-- Attendance sessions: an explicit "check-in window" record layered OVER the
-- existing attendance/excuses/checkin_links tables. The legacy phone/short-code
-- check-in flow is untouched; a short_link session wraps the checkin_links row
-- it opened so both views stay consistent.

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'short_link',
    opens_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closes_at TIMESTAMPTZ,
    checkin_link_id UUID REFERENCES checkin_links(id) ON DELETE SET NULL,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT attendance_sessions_mode_check CHECK (mode IN ('qr', 'short_link', 'manual'))
);

CREATE INDEX IF NOT EXISTS ix_attendance_sessions_chapter_id ON attendance_sessions(chapter_id);
CREATE INDEX IF NOT EXISTS ix_attendance_sessions_event_id ON attendance_sessions(event_id);
CREATE INDEX IF NOT EXISTS ix_attendance_sessions_created_at ON attendance_sessions(created_at);

ALTER TABLE attendance_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS attendance_sessions_select_chapter ON attendance_sessions;
CREATE POLICY attendance_sessions_select_chapter ON attendance_sessions
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());
