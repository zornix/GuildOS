-- Dues run (#50/#45): a bulk invoice batch needs a due date, otherwise the
-- invoice a member opens has nothing to say about when it is due.
--
-- Additive only: `due_at` and `issued_by` are read off each item and default to
-- NULL / the actor, so every existing caller keeps working unchanged. Mirrors
-- what tr_create_invoice_v2 (0120) already writes for a single invoice.

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
    v_member_id UUID;
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
        v_member_id := (v_item->>'member_id')::UUID;
        IF NOT EXISTS (SELECT 1 FROM members WHERE id = v_member_id AND chapter_id = p_chapter_id) THEN
            RAISE EXCEPTION 'member % is not in chapter %', v_member_id, p_chapter_id;
        END IF;

        INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status, description,
                                     due_at, issued_by)
        VALUES (
            p_chapter_id,
            v_member_id,
            v_item->>'kind',
            (v_item->>'amount_cents')::BIGINT,
            'unpaid',
            v_item->>'description',
            (v_item->>'due_at')::TIMESTAMPTZ,
            p_actor_id
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

-- Same exposure rule as every other RPC (0153): backend connection only.
REVOKE ALL ON FUNCTION tr_bulk_create_invoices(UUID, JSONB, UUID, TEXT) FROM PUBLIC;

DO $$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format(
                'REVOKE ALL ON FUNCTION tr_bulk_create_invoices(UUID, JSONB, UUID, TEXT) FROM %I',
                v_role
            );
        END IF;
    END LOOP;
END
$$;
