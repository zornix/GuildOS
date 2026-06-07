-- Chunk C · Payment Review & Receipts: the receipts table (immutable, append-only).
-- A receipt is the permanent record issued when a payment is verified. It is never
-- updated and never deleted (Chunk 0's tr_block_delete / tr_block_audit_log_mutation
-- triggers are reused). One receipt per verified payment (UNIQUE).

CREATE TABLE IF NOT EXISTS receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id),
    verified_payment_id UUID NOT NULL UNIQUE REFERENCES verified_payments(id),
    member_id UUID NOT NULL REFERENCES members(id),
    invoice_id UUID NOT NULL REFERENCES unpaid_invoices(id),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    issued_by UUID REFERENCES members(id),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_receipts_chapter_id ON receipts(chapter_id);
CREATE INDEX IF NOT EXISTS ix_receipts_member_id ON receipts(member_id);
CREATE INDEX IF NOT EXISTS ix_receipts_invoice_id ON receipts(invoice_id);

-- Immutability: reuse Chunk 0's append-only trigger functions (do not redefine).
DROP TRIGGER IF EXISTS receipts_no_delete ON receipts;
CREATE TRIGGER receipts_no_delete
    BEFORE DELETE ON receipts
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS receipts_no_update ON receipts;
CREATE TRIGGER receipts_no_update
    BEFORE UPDATE ON receipts
    FOR EACH ROW EXECUTE FUNCTION tr_block_audit_log_mutation();

-- RLS: a member sees their own receipts; treasury readers see all in their chapter.
ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS receipts_select ON receipts;
CREATE POLICY receipts_select ON receipts
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );
