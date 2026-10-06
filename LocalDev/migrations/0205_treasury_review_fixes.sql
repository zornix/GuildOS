-- Treasury review fixes: refunded cents cannot be reallocated, and record-payment
-- owns a payload-checked idempotency operation with namespaced inner keys.
-- Bodies copied from 0165 and 0170; existing function privileges are preserved.

CREATE OR REPLACE FUNCTION tr_reallocate_payment(
    p_chapter_id UUID,
    p_verified_payment_id UUID,
    p_allocations JSONB,
    p_actor_id UUID,
    p_reason TEXT,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_vp verified_payments%ROWTYPE;
    v_row payment_allocations%ROWTYPE;
    v_item JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_invoice_id UUID;
    v_amount BIGINT;
    v_total BIGINT := 0;
    v_allocatable BIGINT;
    v_affected UUID[] := ARRAY[]::UUID[];
    v_id UUID;
    v_result JSONB;
BEGIN
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason is required to reallocate a payment';
    END IF;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'reallocate_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_allocations IS NULL OR jsonb_typeof(p_allocations) <> 'array' THEN
        RAISE EXCEPTION 'p_allocations must be a JSON array';
    END IF;

    SELECT * INTO v_vp FROM verified_payments
     WHERE id = p_verified_payment_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'verified payment % not found in chapter %', p_verified_payment_id, p_chapter_id;
    END IF;

    -- F-029 belt: coverage must live in payment_allocations only (0165).
    IF v_vp.invoice_id IS NOT NULL THEN
        RAISE EXCEPTION 'verified payment % still covers invoice % directly; move it to payment_allocations first (0165)',
            p_verified_payment_id, v_vp.invoice_id;
    END IF;

    -- Match tr_issue_refund's active-refund cap while holding the same payment lock.
    SELECT v_vp.amount_cents - COALESCE(SUM(amount_cents), 0)
      INTO v_allocatable FROM refunds
     WHERE verified_payment_id = p_verified_payment_id AND status = 'active';

    SELECT COALESCE(SUM((item->>'amount_cents')::BIGINT), 0) INTO v_total
      FROM jsonb_array_elements(p_allocations) AS item;
    IF v_total > v_allocatable THEN
        RAISE EXCEPTION 'allocations total (%) exceeds the verified amount (%)', v_total, v_allocatable;
    END IF;

    -- (a) append a reversal for every live (un-reversed, original) allocation.
    FOR v_row IN
        SELECT * FROM payment_allocations pa
         WHERE pa.verified_payment_id = p_verified_payment_id
           AND pa.reverses_allocation_id IS NULL
           AND NOT EXISTS (
                SELECT 1 FROM payment_allocations r
                 WHERE r.reverses_allocation_id = pa.id)
         ORDER BY pa.created_at, pa.id
    LOOP
        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents,
             reverses_allocation_id, allocated_by, note)
        VALUES
            (p_chapter_id, p_verified_payment_id, v_row.invoice_id, v_row.amount_cents,
             v_row.id, p_actor_id, p_reason);
        v_affected := array_append(v_affected, v_row.invoice_id);
    END LOOP;

    -- (b) append the new allocation set.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_allocations)
    LOOP
        v_invoice_id := (v_item->>'invoice_id')::UUID;
        v_amount := (v_item->>'amount_cents')::BIGINT;

        SELECT * INTO v_invoice FROM unpaid_invoices
         WHERE id = v_invoice_id AND chapter_id = p_chapter_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'invoice % not found in chapter %', v_invoice_id, p_chapter_id;
        END IF;
        IF v_invoice.member_id <> v_vp.member_id THEN
            RAISE EXCEPTION 'invoice % does not belong to the paying member', v_invoice_id;
        END IF;
        IF v_invoice.status = 'cancelled' THEN
            RAISE EXCEPTION 'cannot allocate to a cancelled invoice (%)', v_invoice_id;
        END IF;

        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents, allocated_by, note)
        VALUES
            (p_chapter_id, p_verified_payment_id, v_invoice_id, v_amount, p_actor_id, p_reason);
        v_affected := array_append(v_affected, v_invoice_id);
    END LOOP;

    -- (c) recompute every affected invoice's status.
    FOREACH v_id IN ARRAY v_affected
    LOOP
        PERFORM tr_refresh_invoice_status(v_id);
    END LOOP;

    -- (d) audit (action enum is frozen — VERIFY_PAYMENT + op marker; see 0122 note).
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'VERIFY_PAYMENT', p_actor_id, 'verified_payments', p_verified_payment_id,
            jsonb_build_object('op', 'reallocate_payment', 'reason', p_reason,
                               'allocations', p_allocations));

    v_result := jsonb_build_object(
        'verified_payment_id', p_verified_payment_id,
        'allocated_total_cents', v_total,
        'leftover_cents', v_allocatable - v_total);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'reallocate_payment', p_idempotency_key, p_verified_payment_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION tr_record_payment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_amount_cents BIGINT,
    p_method TEXT,
    p_actor_id UUID,
    p_invoice_id UUID DEFAULT NULL,
    p_reference TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_submission JSONB;
    v_existing JSONB;
    v_result JSONB;
    -- Chapter scopes the key; actor is not part of the payment request.
    v_hash TEXT := md5(jsonb_build_array(
        p_member_id, p_amount_cents, p_method, p_invoice_id, p_reference)::text);
    v_stored_hash TEXT;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result, request_hash INTO v_existing, v_stored_hash FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'record_payment' AND key = p_idempotency_key;
        IF FOUND THEN
            IF v_stored_hash IS DISTINCT FROM v_hash THEN
                RAISE EXCEPTION 'idempotency_key_reused: this key was used with a different request';
            END IF;
            RETURN v_existing;
        END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF p_invoice_id IS NOT NULL THEN
        v_submission := tr_submit_payment(
            p_chapter_id, p_member_id, p_invoice_id, p_amount_cents, p_method,
            p_reference, p_actor_id, 'record:' || p_idempotency_key || ':submit');
    ELSE
        v_submission := tr_submit_balance_payment(
            p_chapter_id, p_member_id, p_amount_cents, p_method,
            p_reference, 'record:' || p_idempotency_key || ':submit');
    END IF;

    v_result := tr_verify_payment_v2(
        p_chapter_id, (v_submission->>'id')::UUID, p_actor_id, 'record:' || p_idempotency_key || ':verify');
    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result, request_hash)
        VALUES (p_chapter_id, 'record_payment', p_idempotency_key, (v_result->>'id')::UUID,
                v_result || jsonb_build_object('_created', false), v_hash);
    END IF;

    RETURN v_result;
END;
$$;

-- Same exposure rule as every other RPC (0153): backend connection only.
REVOKE ALL ON FUNCTION tr_record_payment(UUID, UUID, BIGINT, TEXT, UUID, UUID, TEXT, TEXT) FROM PUBLIC;

DO $$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format(
                'REVOKE ALL ON FUNCTION tr_record_payment(UUID, UUID, BIGINT, TEXT, UUID, UUID, TEXT, TEXT) FROM %I',
                v_role
            );
        END IF;
    END LOOP;
END
$$;
