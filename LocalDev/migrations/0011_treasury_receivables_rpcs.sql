-- Chunk A · Receivables RPCs: tr_create_invoice, tr_submit_payment,
-- tr_cancel_invoice, tr_bulk_create_invoices. Each is one plpgsql txn (atomic).

-- ── create one invoice + ledger + audit, atomically ──────────────────────────
CREATE OR REPLACE FUNCTION tr_create_invoice(
    p_chapter_id UUID,
    p_member_id UUID,
    p_kind TEXT,
    p_amount_cents BIGINT,
    p_description TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL,
    p_source_event_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'create_invoice' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status, description, source_event_id)
    VALUES (p_chapter_id, p_member_id, p_kind, p_amount_cents, 'unpaid', p_description, p_source_event_id)
    RETURNING * INTO v_invoice;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'INVOICE_CREATED', p_amount_cents, p_member_id, 'unpaid_invoices', v_invoice.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_INVOICE', p_actor_id, 'unpaid_invoices', v_invoice.id,
            jsonb_build_object('kind', p_kind, 'amount_cents', p_amount_cents));

    v_result := to_jsonb(v_invoice);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'create_invoice', p_idempotency_key, v_invoice.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── submit a payment proof (pending; NO ledger, NO money) ─────────────────────
CREATE OR REPLACE FUNCTION tr_submit_payment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_invoice_id UUID,
    p_claimed_amount_cents BIGINT,
    p_method TEXT,
    p_proof_ref TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_submission payment_submissions%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'submit_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_invoice FROM unpaid_invoices
     WHERE id = p_invoice_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invoice % not found in chapter %', p_invoice_id, p_chapter_id;
    END IF;
    IF v_invoice.status = 'cancelled' THEN
        RAISE EXCEPTION 'cannot submit payment against a cancelled invoice';
    END IF;
    IF v_invoice.status = 'paid' THEN
        RAISE EXCEPTION 'invoice is already fully paid';
    END IF;

    INSERT INTO payment_submissions
        (chapter_id, member_id, invoice_id, claimed_amount_cents, method, proof_ref, status)
    VALUES
        (p_chapter_id, p_member_id, p_invoice_id, p_claimed_amount_cents, p_method, p_proof_ref, 'pending')
    RETURNING * INTO v_submission;

    v_result := to_jsonb(v_submission);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'submit_payment', p_idempotency_key, v_submission.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── cancel an UNPAID invoice (idempotent) ────────────────────────────────────
CREATE OR REPLACE FUNCTION tr_cancel_invoice(
    p_chapter_id UUID,
    p_invoice_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice unpaid_invoices%ROWTYPE;
BEGIN
    SELECT * INTO v_invoice FROM unpaid_invoices
     WHERE id = p_invoice_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invoice % not found in chapter %', p_invoice_id, p_chapter_id;
    END IF;

    IF v_invoice.status = 'cancelled' THEN
        RETURN to_jsonb(v_invoice);  -- idempotent no-op
    END IF;
    IF v_invoice.status <> 'unpaid' THEN
        RAISE EXCEPTION 'only unpaid invoices may be cancelled (status=%); use an adjustment or refund', v_invoice.status;
    END IF;

    UPDATE unpaid_invoices SET status = 'cancelled' WHERE id = p_invoice_id
    RETURNING * INTO v_invoice;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'CANCEL_INVOICE', -v_invoice.amount_cents, v_invoice.member_id,
            'unpaid_invoices', v_invoice.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CANCEL_INVOICE', p_actor_id, 'unpaid_invoices', v_invoice.id, '{}'::jsonb);

    RETURN to_jsonb(v_invoice);
END;
$$;

-- ── atomic bulk invoice creation (all-or-nothing) ────────────────────────────
-- p_invoices: jsonb array of {member_id, kind, amount_cents, description}.
CREATE OR REPLACE FUNCTION tr_bulk_create_invoices(
    p_chapter_id UUID,
    p_invoices JSONB,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_item JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_ids UUID[] := ARRAY[]::UUID[];
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'bulk_create_invoices' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF jsonb_typeof(p_invoices) <> 'array' THEN
        RAISE EXCEPTION 'p_invoices must be a JSON array';
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_invoices)
    LOOP
        INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status, description)
        VALUES (
            p_chapter_id,
            (v_item->>'member_id')::UUID,
            v_item->>'kind',
            (v_item->>'amount_cents')::BIGINT,
            'unpaid',
            v_item->>'description'
        )
        RETURNING * INTO v_invoice;

        INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
        VALUES (p_chapter_id, 'INVOICE_CREATED', v_invoice.amount_cents, v_invoice.member_id,
                'unpaid_invoices', v_invoice.id, 'active');

        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'CREATE_INVOICE', p_actor_id, 'unpaid_invoices', v_invoice.id,
                jsonb_build_object('bulk', true, 'kind', v_invoice.kind, 'amount_cents', v_invoice.amount_cents));

        v_ids := array_append(v_ids, v_invoice.id);
    END LOOP;

    v_result := jsonb_build_object('count', array_length(v_ids, 1), 'invoice_ids', to_jsonb(v_ids));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'bulk_create_invoices', p_idempotency_key, NULL, v_result);
    END IF;

    RETURN v_result;
END;
$$;
