-- TREASURY V1 · tr_void_invoice (decision #5): Treasurer-only void/waive with a
-- MANDATORY reason. Mirrors tr_cancel_invoice (0011) but:
--   - reason is required and recorded in audit_logs metadata,
--   - allowed on BOTH 'unpaid' and 'partially_paid' invoices (an invoice that is
--     partially covered can still be waived; already-applied payments remain as
--     member credit because balances are computed, never stored).
-- Append-only correction pattern: the CANCEL_INVOICE ledger entry references the
-- invoice; nothing is deleted or rewritten.
--
-- Audit action reuses 'CANCEL_INVOICE' (the audit_logs action CHECK is shared
-- infrastructure; reuse over widening, per docs/TREASURY_ARCHITECTURE.md §2).
-- metadata.op='void' + metadata.reason distinguish V1 voids.

CREATE OR REPLACE FUNCTION tr_void_invoice(
    p_chapter_id UUID,
    p_invoice_id UUID,
    p_actor_id UUID,
    p_reason TEXT,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason is required to void an invoice';
    END IF;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'void_invoice' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_invoice FROM unpaid_invoices
     WHERE id = p_invoice_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invoice % not found in chapter %', p_invoice_id, p_chapter_id;
    END IF;

    IF v_invoice.status = 'cancelled' THEN
        RETURN to_jsonb(v_invoice);  -- idempotent no-op
    END IF;
    IF v_invoice.status NOT IN ('unpaid', 'partially_paid') THEN
        RAISE EXCEPTION 'only unpaid or partially_paid invoices may be voided (status=%)', v_invoice.status;
    END IF;

    UPDATE unpaid_invoices SET status = 'cancelled' WHERE id = p_invoice_id
    RETURNING * INTO v_invoice;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'CANCEL_INVOICE', -v_invoice.amount_cents, v_invoice.member_id,
            'unpaid_invoices', v_invoice.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CANCEL_INVOICE', p_actor_id, 'unpaid_invoices', v_invoice.id,
            jsonb_build_object('op', 'void', 'reason', p_reason));

    v_result := to_jsonb(v_invoice);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'void_invoice', p_idempotency_key, v_invoice.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
