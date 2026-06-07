-- Chunk D · Expenses: chapter_expenses (money leaving the chapter). Range 0040-0049.

CREATE TABLE IF NOT EXISTS chapter_expenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    amount_cents BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chapter_expenses_category_check
        CHECK (category IN ('event', 'supplies', 'philanthropy', 'maintenance')),
    CONSTRAINT chapter_expenses_amount_check CHECK (amount_cents > 0),
    CONSTRAINT chapter_expenses_status_check CHECK (status IN ('active', 'invalidated'))
);

CREATE INDEX IF NOT EXISTS ix_chapter_expenses_chapter_id ON chapter_expenses(chapter_id);
CREATE INDEX IF NOT EXISTS ix_chapter_expenses_status ON chapter_expenses(status);

ALTER TABLE chapter_expenses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS chapter_expenses_select ON chapter_expenses;
CREATE POLICY chapter_expenses_select ON chapter_expenses
    FOR SELECT USING (treasury_has_capability(chapter_id, 'treasury:read'));
