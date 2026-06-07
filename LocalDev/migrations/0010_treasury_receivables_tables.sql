-- Chunk A · Receivables: unpaid_invoices, payment_submissions, verified_payments skeleton.
-- Migration range 0010-0019. Idempotent (shared demo may be re-migrated).

-- ── unpaid_invoices: money owed to the chapter ───────────────────────────────
CREATE TABLE IF NOT EXISTS unpaid_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    amount_cents BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid',
    description TEXT,
    legacy_fine_id UUID,
    source_event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unpaid_invoices_kind_check
        CHECK (kind IN ('dues', 'rent', 'utilities', 'fine', 'assessment')),
    CONSTRAINT unpaid_invoices_amount_check CHECK (amount_cents > 0),
    CONSTRAINT unpaid_invoices_status_check
        CHECK (status IN ('unpaid', 'partially_paid', 'paid', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_unpaid_invoices_chapter_id ON unpaid_invoices(chapter_id);
CREATE INDEX IF NOT EXISTS ix_unpaid_invoices_member_id ON unpaid_invoices(member_id);
CREATE INDEX IF NOT EXISTS ix_unpaid_invoices_status ON unpaid_invoices(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_unpaid_invoices_legacy_fine_id
    ON unpaid_invoices(legacy_fine_id) WHERE legacy_fine_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_unpaid_invoices_source_event_id
    ON unpaid_invoices(source_event_id) WHERE source_event_id IS NOT NULL;

-- ── payment_submissions: a member's proof of payment (no money until approved) ─
CREATE TABLE IF NOT EXISTS payment_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL REFERENCES unpaid_invoices(id) ON DELETE CASCADE,
    claimed_amount_cents BIGINT NOT NULL,
    method TEXT NOT NULL,
    proof_ref TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT payment_submissions_amount_check CHECK (claimed_amount_cents > 0),
    CONSTRAINT payment_submissions_method_check
        CHECK (method IN ('venmo', 'zelle', 'cash', 'bank_transfer')),
    CONSTRAINT payment_submissions_status_check
        CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_chapter_id ON payment_submissions(chapter_id);
CREATE INDEX IF NOT EXISTS ix_payment_submissions_member_id ON payment_submissions(member_id);
CREATE INDEX IF NOT EXISTS ix_payment_submissions_invoice_id ON payment_submissions(invoice_id);
CREATE INDEX IF NOT EXISTS ix_payment_submissions_status ON payment_submissions(status);

-- ── verified_payments: SKELETON (Chunk A ships DDL; Chunk C's verify RPC populates it) ─
-- submission_id is UNIQUE (one verified payment per submission) and nullable so the
-- fines migration can record a historical paid fine with no originating submission.
CREATE TABLE IF NOT EXISTS verified_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL REFERENCES unpaid_invoices(id) ON DELETE CASCADE,
    submission_id UUID REFERENCES payment_submissions(id) ON DELETE SET NULL,
    amount_cents BIGINT NOT NULL,
    verified_by UUID REFERENCES members(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT verified_payments_amount_check CHECK (amount_cents > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_verified_payments_submission_id
    ON verified_payments(submission_id) WHERE submission_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_verified_payments_chapter_id ON verified_payments(chapter_id);
CREATE INDEX IF NOT EXISTS ix_verified_payments_member_id ON verified_payments(member_id);
CREATE INDEX IF NOT EXISTS ix_verified_payments_invoice_id ON verified_payments(invoice_id);

-- ── RLS: default-deny, chapter-scoped, capability-aware (Chunk 0 pattern) ─────
ALTER TABLE unpaid_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE verified_payments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS unpaid_invoices_select ON unpaid_invoices;
CREATE POLICY unpaid_invoices_select ON unpaid_invoices
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

DROP POLICY IF EXISTS payment_submissions_select ON payment_submissions;
CREATE POLICY payment_submissions_select ON payment_submissions
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'payment:review')
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

DROP POLICY IF EXISTS verified_payments_select ON verified_payments;
CREATE POLICY verified_payments_select ON verified_payments
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );
