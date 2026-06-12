-- Recruitment CRM: a minimal pipeline of recruits (PNMs).

CREATE TABLE IF NOT EXISTS recruits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    stage TEXT NOT NULL DEFAULT 'lead',
    notes TEXT,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT recruits_stage_check CHECK (
        stage IN ('lead', 'contacted', 'attended_event', 'bid_extended', 'bid_accepted', 'dropped')
    )
);

CREATE INDEX IF NOT EXISTS ix_recruits_chapter_id ON recruits(chapter_id);
CREATE INDEX IF NOT EXISTS ix_recruits_stage ON recruits(stage);
CREATE INDEX IF NOT EXISTS ix_recruits_created_at ON recruits(created_at);

ALTER TABLE recruits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS recruits_select_chapter ON recruits;
CREATE POLICY recruits_select_chapter ON recruits
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());
