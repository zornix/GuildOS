-- TREASURY V1 · Invoice model: due_at, issued_by, 'manual' kind, line items,
-- and tr_create_invoice_v2 (mirrors tr_create_invoice/0080 with the new columns).
-- SPEC §5 Invoices: member, line items, amount, issued_at, due_at, source, issued_by.

-- ── unpaid_invoices: new columns ──────────────────────────────────────────────
ALTER TABLE unpaid_invoices ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ NULL;
ALTER TABLE unpaid_invoices
    ADD COLUMN IF NOT EXISTS issued_by UUID NULL REFERENCES members(id) ON DELETE SET NULL;

-- kind gains 'manual' (drop+recreate keeping every existing value).
ALTER TABLE unpaid_invoices DROP CONSTRAINT IF EXISTS unpaid_invoices_kind_check;
ALTER TABLE unpaid_invoices ADD CONSTRAINT unpaid_invoices_kind_check
    CHECK (kind IN ('dues', 'rent', 'utilities', 'fine', 'assessment', 'manual'));

CREATE INDEX IF NOT EXISTS ix_unpaid_invoices_due_at
    ON unpaid_invoices(due_at) WHERE due_at IS NOT NULL;

-- ── invoice_line_items: append-only breakdown of an invoice ──────────────────
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL REFERENCES unpaid_invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_invoice_line_items_chapter_id ON invoice_line_items(chapter_id);
CREATE INDEX IF NOT EXISTS ix_invoice_line_items_invoice_id ON invoice_line_items(invoice_id);

-- Immutability: reuse Chunk 0's append-only trigger functions (0005).
DROP TRIGGER IF EXISTS invoice_line_items_no_delete ON invoice_line_items;
CREATE TRIGGER invoice_line_items_no_delete
    BEFORE DELETE ON invoice_line_items
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS invoice_line_items_no_update ON invoice_line_items;
CREATE TRIGGER invoice_line_items_no_update
    BEFORE UPDATE ON invoice_line_items
    FOR EACH ROW EXECUTE FUNCTION tr_block_audit_log_mutation();

-- RLS: a member sees their own invoice's line items; treasury readers see all.
ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS invoice_line_items_select ON invoice_line_items;
CREATE POLICY invoice_line_items_select ON invoice_line_items
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM unpaid_invoices ui
            WHERE ui.id = invoice_line_items.invoice_id
              AND ui.member_id = treasury_request_member_id()
        )
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

-- ── tr_create_invoice_v2: invoice + line items + ledger + audit, atomically ──
-- Mirrors tr_create_invoice (0011/0080) and adds due_at / issued_by / line items.
-- If p_line_items is supplied, the items' sum MUST equal p_amount_cents.
CREATE OR REPLACE FUNCTION tr_create_invoice_v2(
    p_chapter_id UUID,
    p_member_id UUID,
    p_kind TEXT,
    p_amount_cents BIGINT,
    p_description TEXT,
    p_actor_id UUID,
    p_due_at TIMESTAMPTZ DEFAULT NULL,
    p_issued_by UUID DEFAULT NULL,
    p_line_items JSONB DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL,
    p_source_event_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_issued_by UUID;
    v_item JSONB;
    v_items_sum BIGINT := 0;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'create_invoice_v2' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- tenant guard (0080 pattern)
    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    v_issued_by := COALESCE(p_issued_by, p_actor_id);

    IF p_line_items IS NOT NULL THEN
        IF jsonb_typeof(p_line_items) <> 'array' THEN
            RAISE EXCEPTION 'p_line_items must be a JSON array';
        END IF;
        SELECT COALESCE(SUM((item->>'amount_cents')::BIGINT), 0) INTO v_items_sum
          FROM jsonb_array_elements(p_line_items) AS item;
        IF v_items_sum <> p_amount_cents THEN
            RAISE EXCEPTION 'line items sum (%) must equal amount_cents (%)', v_items_sum, p_amount_cents;
        END IF;
    END IF;

    INSERT INTO unpaid_invoices
        (chapter_id, member_id, kind, amount_cents, status, description,
         source_event_id, due_at, issued_by)
    VALUES
        (p_chapter_id, p_member_id, p_kind, p_amount_cents, 'unpaid', p_description,
         p_source_event_id, p_due_at, v_issued_by)
    RETURNING * INTO v_invoice;

    IF p_line_items IS NOT NULL THEN
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_line_items)
        LOOP
            INSERT INTO invoice_line_items (chapter_id, invoice_id, description, amount_cents)
            VALUES (p_chapter_id, v_invoice.id, v_item->>'description',
                    (v_item->>'amount_cents')::BIGINT);
        END LOOP;
    END IF;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'INVOICE_CREATED', p_amount_cents, p_member_id, 'unpaid_invoices', v_invoice.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_INVOICE', p_actor_id, 'unpaid_invoices', v_invoice.id,
            jsonb_build_object('kind', p_kind, 'amount_cents', p_amount_cents,
                               'due_at', p_due_at, 'issued_by', v_issued_by,
                               'line_item_count', COALESCE(jsonb_array_length(p_line_items), 0)));

    v_result := to_jsonb(v_invoice);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'create_invoice_v2', p_idempotency_key, v_invoice.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
