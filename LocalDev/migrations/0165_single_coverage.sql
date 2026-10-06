-- F-029 · Invoice coverage lives only in payment_allocations.
--
-- A legacy verification (0031) and every paid fine migrated by 0012 stored
-- coverage on verified_payments.invoice_id; v2 (0124) stores it in
-- payment_allocations. Reallocating a payment that still had the direct link
-- counted its cents twice. This migration:
--   1. moves every direct link into an allocation row and nulls the column
--      (coverage moves, money does not: the total remaining over the affected
--      open invoices is checked before and after);
--   2. drops the direct term from tr_invoice_remaining_cents;
--   3. makes tr_verify_payment (v1) validate as before and then delegate to
--      tr_verify_payment_v2, so it no longer writes invoice_id or status;
--   4. makes tr_reallocate_payment refuse a payment that still has a direct link.
-- Safe to run twice: step 1 finds nothing once the column is NULL.

-- >>> 0165 data
DO $$
DECLARE
    v_ids UUID[];
    v_before BIGINT;
    v_after BIGINT;
BEGIN
    -- Only invoices with a direct link can change; checking just those keeps
    -- concurrent writes elsewhere out of the comparison. Remaining is computed
    -- inline (direct term included) so the check means the same thing whichever
    -- version of tr_invoice_remaining_cents is live.
    v_ids := ARRAY(SELECT DISTINCT invoice_id FROM verified_payments WHERE invoice_id IS NOT NULL);

    SELECT COALESCE(SUM(ui.amount_cents
             - COALESCE((SELECT SUM(vp.amount_cents) FROM verified_payments vp
                          WHERE vp.invoice_id = ui.id), 0)
             - tr_net_allocated_cents(ui.id)), 0)
      INTO v_before
      FROM unpaid_invoices ui
     WHERE ui.id = ANY(v_ids) AND ui.status <> 'cancelled';

    INSERT INTO payment_allocations (chapter_id, verified_payment_id, invoice_id, amount_cents, note)
    SELECT vp.chapter_id, vp.id, vp.invoice_id, vp.amount_cents,
           'migrated from verified_payments.invoice_id (0165)'
      FROM verified_payments vp
     WHERE vp.invoice_id IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM payment_allocations pa
             WHERE pa.verified_payment_id = vp.id AND pa.invoice_id = vp.invoice_id);

    UPDATE verified_payments vp SET invoice_id = NULL
     WHERE vp.invoice_id IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM payment_allocations pa
             WHERE pa.verified_payment_id = vp.id AND pa.invoice_id = vp.invoice_id);

    SELECT COALESCE(SUM(ui.amount_cents
             - COALESCE((SELECT SUM(vp.amount_cents) FROM verified_payments vp
                          WHERE vp.invoice_id = ui.id), 0)
             - tr_net_allocated_cents(ui.id)), 0)
      INTO v_after
      FROM unpaid_invoices ui
     WHERE ui.id = ANY(v_ids) AND ui.status <> 'cancelled';

    IF v_before IS DISTINCT FROM v_after THEN
        RAISE EXCEPTION '0165: remaining cents changed (% before, % after)', v_before, v_after;
    END IF;
END
$$;
-- <<< 0165 data

-- Remaining = amount − net allocations (coverage has one home now).
CREATE OR REPLACE FUNCTION tr_invoice_remaining_cents(p_invoice_id UUID)
RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT ui.amount_cents - tr_net_allocated_cents(ui.id)
    FROM unpaid_invoices ui
    WHERE ui.id = p_invoice_id
$$;

-- ── tr_verify_payment (v1): same validation, v2 writes ───────────────────────
CREATE OR REPLACE FUNCTION tr_verify_payment(
    p_chapter_id UUID,
    p_submission_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_submission payment_submissions%ROWTYPE;
    v_existing_vp verified_payments%ROWTYPE;
BEGIN
    -- Keys stored by the old v1 body still replay.
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'verify_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_submission FROM payment_submissions
     WHERE id = p_submission_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'submission % not found in chapter %', p_submission_id, p_chapter_id;
    END IF;

    IF v_submission.status = 'approved' THEN
        SELECT * INTO v_existing_vp FROM verified_payments
         WHERE submission_id = p_submission_id;
        RETURN to_jsonb(v_existing_vp) || jsonb_build_object('_created', false);
    END IF;
    IF v_submission.status = 'rejected' THEN
        RAISE EXCEPTION 'submission % was rejected and cannot be verified', p_submission_id;
    END IF;

    -- v1 only ever verified invoice-targeted submissions.
    IF NOT EXISTS (SELECT 1 FROM unpaid_invoices
                    WHERE id = v_submission.invoice_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'invoice % not found in chapter %', v_submission.invoice_id, p_chapter_id;
    END IF;

    RETURN tr_verify_payment_v2(p_chapter_id, p_submission_id, p_actor_id, p_idempotency_key);
END;
$$;

-- ── tr_reallocate_payment: refuse a payment that still has a direct link ─────
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

    SELECT COALESCE(SUM((item->>'amount_cents')::BIGINT), 0) INTO v_total
      FROM jsonb_array_elements(p_allocations) AS item;
    IF v_total > v_vp.amount_cents THEN
        RAISE EXCEPTION 'allocations total (%) exceeds the verified amount (%)', v_total, v_vp.amount_cents;
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
        'leftover_cents', v_vp.amount_cents - v_total);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'reallocate_payment', p_idempotency_key, p_verified_payment_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
