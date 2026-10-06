-- F-070 · A reused dues-run idempotency key with a different payload is
-- rejected (decision D11).
--
-- tr_bulk_create_invoices (live body from 0158) replayed the stored result for
-- any request carrying a known key, so an edited dues run with the same key was
-- silently ignored. Now the request is hashed and stored with the key; a replay
-- whose hash differs raises idempotency_key_reused. Keys stored before this
-- migration have no hash and replay as before. jsonb::text is canonical, so key
-- order in the items does not change the hash.

-- ponytail: only tr_bulk_create_invoices checks request_hash and keys never expire; extend per RPC and add a purge job when the table matters.
ALTER TABLE idempotency_keys ADD COLUMN IF NOT EXISTS request_hash TEXT;

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
    -- Every payload argument except the key and the actor (chapter scopes the key).
    v_hash TEXT := md5(COALESCE(p_invoices::text, ''));
    v_stored_hash TEXT;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result, request_hash INTO v_existing, v_stored_hash FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'bulk_create_invoices' AND key = p_idempotency_key;
        IF FOUND THEN
            IF v_stored_hash IS NOT NULL AND v_stored_hash <> v_hash THEN
                RAISE EXCEPTION 'idempotency_key_reused: this key was used with a different request';
            END IF;
            RETURN v_existing;
        END IF;
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
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result, request_hash)
        VALUES (p_chapter_id, 'bulk_create_invoices', p_idempotency_key, NULL, v_result, v_hash);
    END IF;

    RETURN v_result;
END;
$$;
