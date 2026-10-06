-- F-048 / D13: usage rows may be deleted (retention, chapter cascade) but not
-- updated. member_id was ON DELETE SET NULL, which is an UPDATE the trigger
-- still rejects, so a member delete stayed blocked — cascade instead.

DROP TRIGGER IF EXISTS usage_events_immutable ON usage_events;
CREATE TRIGGER usage_events_immutable
    BEFORE UPDATE ON usage_events
    FOR EACH ROW EXECUTE FUNCTION ux_block_usage_events_mutation();

CREATE INDEX IF NOT EXISTS ix_usage_events_member_created
    ON usage_events(member_id, created_at);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'usage_events_member_id_fkey'
           AND confdeltype <> 'c'
    ) THEN
        ALTER TABLE usage_events DROP CONSTRAINT usage_events_member_id_fkey;
        ALTER TABLE usage_events
            ADD CONSTRAINT usage_events_member_id_fkey
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE;
    END IF;
END $$;
