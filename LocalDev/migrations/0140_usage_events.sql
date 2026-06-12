-- Instrumentation V1 (GreekOS spec build-order #6): lightweight usage events.
-- Append-only, tenant-scoped, fire-and-forget writes from the API layer.
-- The calendar domain (a VIEW, not an entity — spec §2) owns NO tables; this
-- is the only table the calendar/instrumentation work introduces.

CREATE TABLE IF NOT EXISTS usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    event_name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_usage_events_chapter_id ON usage_events(chapter_id);
CREATE INDEX IF NOT EXISTS ix_usage_events_event_name ON usage_events(chapter_id, event_name);
CREATE INDEX IF NOT EXISTS ix_usage_events_created_at ON usage_events(created_at);

-- RLS: same tenant discipline as every other chapter-scoped table.
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS usage_events_select_chapter ON usage_events;
CREATE POLICY usage_events_select_chapter ON usage_events
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- Append-only: same discipline as task_commitment_log / big_ledger.
CREATE OR REPLACE FUNCTION ux_block_usage_events_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'usage_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS usage_events_immutable ON usage_events;
CREATE TRIGGER usage_events_immutable
    BEFORE UPDATE OR DELETE ON usage_events
    FOR EACH ROW EXECUTE FUNCTION ux_block_usage_events_mutation();
