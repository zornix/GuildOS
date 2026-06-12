-- NL chapter controller: approval-gated command requests. There is NO parser —
-- proposed_actions stays empty until a real one exists, and execution only ever
-- calls existing service APIs (never duplicates their logic).

CREATE TABLE IF NOT EXISTS command_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    requested_by UUID REFERENCES members(id) ON DELETE SET NULL,
    input_text TEXT NOT NULL,
    proposed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending_approval',
    reviewed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT command_requests_status_check CHECK (
        status IN ('pending_approval', 'approved', 'rejected', 'executed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS ix_command_requests_chapter_id ON command_requests(chapter_id);
CREATE INDEX IF NOT EXISTS ix_command_requests_status ON command_requests(status);
CREATE INDEX IF NOT EXISTS ix_command_requests_created_at ON command_requests(created_at);

ALTER TABLE command_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS command_requests_select_chapter ON command_requests;
CREATE POLICY command_requests_select_chapter ON command_requests
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());
