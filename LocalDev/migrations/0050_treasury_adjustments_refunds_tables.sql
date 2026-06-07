-- Chunk E · Adjustments & Refunds tables. Migration range 0050-0059.
-- Idempotent (the shared demo may be re-migrated).
--
-- finance_adjustments: manual corrections that move a balance, with a paper trail.
--   member_id NULL = chapter-level. delta_cents is SIGNED (no positivity check).
--   reason + officer_id are mandatory. status pending|active supports the optional
--   two-officer sign-off above a threshold: a 'pending' adjustment has NO balance
--   effect until a second officer activates it (Slice 9 governance).
-- refunds: return money to a member against exactly one verified payment, capped at
--   that payment's amount. Corrected via invalidation, never deleted (invariant 1).

CREATE TABLE IF NOT EXISTS finance_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    delta_cents BIGINT NOT NULL,
    reason TEXT NOT NULL,
    officer_id UUID NOT NULL REFERENCES members(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    approved_by UUID REFERENCES members(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT finance_adjustments_kind_check
        CHECK (kind IN ('waive_fine', 'rent_correction', 'dues_forgiveness', 'manual_correction')),
    CONSTRAINT finance_adjustments_reason_check CHECK (length(btrim(reason)) > 0),
    CONSTRAINT finance_adjustments_status_check CHECK (status IN ('pending', 'active'))
);

CREATE INDEX IF NOT EXISTS ix_finance_adjustments_chapter_id ON finance_adjustments(chapter_id);
CREATE INDEX IF NOT EXISTS ix_finance_adjustments_member_id ON finance_adjustments(member_id);
CREATE INDEX IF NOT EXISTS ix_finance_adjustments_status ON finance_adjustments(status);

CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    verified_payment_id UUID NOT NULL REFERENCES verified_payments(id) ON DELETE CASCADE,
    amount_cents BIGINT NOT NULL,
    reason TEXT NOT NULL,
    officer_id UUID NOT NULL REFERENCES members(id) ON DELETE SET NULL,
    reviewed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT refunds_amount_check CHECK (amount_cents > 0),
    CONSTRAINT refunds_reason_check CHECK (length(btrim(reason)) > 0),
    CONSTRAINT refunds_status_check CHECK (status IN ('active', 'invalidated'))
);

CREATE INDEX IF NOT EXISTS ix_refunds_chapter_id ON refunds(chapter_id);
CREATE INDEX IF NOT EXISTS ix_refunds_member_id ON refunds(member_id);
CREATE INDEX IF NOT EXISTS ix_refunds_verified_payment_id ON refunds(verified_payment_id);
CREATE INDEX IF NOT EXISTS ix_refunds_status ON refunds(status);

-- Invariant 1: finance records are never hard-deleted. Reuse Chunk 0's tr_block_delete.
DROP TRIGGER IF EXISTS finance_adjustments_no_delete ON finance_adjustments;
CREATE TRIGGER finance_adjustments_no_delete
    BEFORE DELETE ON finance_adjustments
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS refunds_no_delete ON refunds;
CREATE TRIGGER refunds_no_delete
    BEFORE DELETE ON refunds
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

-- RLS: default-deny, chapter-scoped, capability-aware (Chunk 0 pattern). A member
-- sees their own adjustments/refunds; treasury readers see all in their chapter.
ALTER TABLE finance_adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE refunds ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS finance_adjustments_select ON finance_adjustments;
CREATE POLICY finance_adjustments_select ON finance_adjustments
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

DROP POLICY IF EXISTS refunds_select ON refunds;
CREATE POLICY refunds_select ON refunds
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );
