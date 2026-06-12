-- Calendar extensions on the existing events table (additive, all nullable or
-- defaulted — existing rows and code paths are unaffected).
--
-- Cross-service seams (§7): events link OUT to attendance sessions, task
-- groups, announcements, and (future) budgets via nullable FKs.

ALTER TABLE events ADD COLUMN IF NOT EXISTS event_type TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'chapter';
ALTER TABLE events ADD COLUMN IF NOT EXISTS linked_task_group_id UUID REFERENCES task_groups(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS linked_attendance_session_id UUID REFERENCES attendance_sessions(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS linked_announcement_id UUID REFERENCES announcements(id) ON DELETE SET NULL;
-- No budgets table exists yet; plain UUID until treasury grows one.
-- TODO(treasury): add FK once a budgets table exists.
ALTER TABLE events ADD COLUMN IF NOT EXISTS linked_budget_id UUID;

ALTER TABLE events DROP CONSTRAINT IF EXISTS events_visibility_check;
ALTER TABLE events ADD CONSTRAINT events_visibility_check CHECK (
    visibility IN ('chapter', 'officer', 'role_specific', 'private')
);

CREATE INDEX IF NOT EXISTS ix_events_visibility ON events(visibility);
CREATE INDEX IF NOT EXISTS ix_events_linked_task_group_id ON events(linked_task_group_id);
