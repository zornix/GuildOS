-- Chunk B · Member balance cache. Pure cache; never read as truth. Range 0020-0029.

CREATE TABLE IF NOT EXISTS member_finance_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    total_owed_cents BIGINT NOT NULL DEFAULT 0,
    total_paid_cents BIGINT NOT NULL DEFAULT 0,
    outstanding_balance_cents BIGINT NOT NULL DEFAULT 0,
    current_balance_cents BIGINT NOT NULL DEFAULT 0,
    recomputed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_member_finance_accounts_member UNIQUE (member_id)
);

CREATE INDEX IF NOT EXISTS ix_member_finance_accounts_chapter_id ON member_finance_accounts(chapter_id);

ALTER TABLE member_finance_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS member_finance_accounts_select ON member_finance_accounts;
CREATE POLICY member_finance_accounts_select ON member_finance_accounts
    FOR SELECT USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );
