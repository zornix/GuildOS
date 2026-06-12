-- Events V1 model (spec §3): event types, groups, organizers, audience,
-- supervisor + finable flag. Additive — legacy columns (free-text event_type,
-- fine_amount) are untouched.

-- ── Event types (catalog per chapter; unique case-insensitive name) ───────────

CREATE TABLE IF NOT EXISTS event_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_event_types_chapter_lower_name
    ON event_types(chapter_id, lower(name));
CREATE INDEX IF NOT EXISTS ix_event_types_chapter_id ON event_types(chapter_id);

-- ── Event groups (setup → event → cleanup; each member is a full event) ───────

CREATE TABLE IF NOT EXISTS event_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    name TEXT,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_event_groups_chapter_id ON event_groups(chapter_id);

-- ── Organizers (volunteer or assigned; soft minimum enforced in app layer) ────

CREATE TABLE IF NOT EXISTS event_organizers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'volunteer' CHECK (source IN ('volunteer', 'assigned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_organizers_event_member UNIQUE (event_id, member_id)
);

CREATE INDEX IF NOT EXISTS ix_event_organizers_chapter_id ON event_organizers(chapter_id);
CREATE INDEX IF NOT EXISTS ix_event_organizers_event_id ON event_organizers(event_id);
CREATE INDEX IF NOT EXISTS ix_event_organizers_member_id ON event_organizers(member_id);

-- ── Custom audience membership (visibility = 'custom') ────────────────────────

CREATE TABLE IF NOT EXISTS event_audience_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_audience_event_member UNIQUE (event_id, member_id)
);

CREATE INDEX IF NOT EXISTS ix_event_audience_chapter_id ON event_audience_members(chapter_id);
CREATE INDEX IF NOT EXISTS ix_event_audience_event_id ON event_audience_members(event_id);
CREATE INDEX IF NOT EXISTS ix_event_audience_member_id ON event_audience_members(member_id);

-- ── Events columns ─────────────────────────────────────────────────────────────

ALTER TABLE events ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES event_types(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS finable BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE events ADD COLUMN IF NOT EXISTS event_group_id UUID REFERENCES event_groups(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS supervisor_member_id UUID REFERENCES members(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_events_event_type_id ON events(event_type_id);
CREATE INDEX IF NOT EXISTS ix_events_event_group_id ON events(event_group_id);
CREATE INDEX IF NOT EXISTS ix_events_supervisor_member_id ON events(supervisor_member_id);

-- visibility gains 'custom' (resolved decision #4); old values stay valid.
ALTER TABLE events DROP CONSTRAINT IF EXISTS events_visibility_check;
ALTER TABLE events ADD CONSTRAINT events_visibility_check CHECK (
    visibility IN ('chapter', 'officer', 'role_specific', 'private', 'custom')
);

-- ── RLS (chapter-scoped reads; writes go through service-role RPCs) ───────────

ALTER TABLE event_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_organizers ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_audience_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_types_select_chapter ON event_types;
CREATE POLICY event_types_select_chapter ON event_types
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS event_groups_select_chapter ON event_groups;
CREATE POLICY event_groups_select_chapter ON event_groups
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS event_organizers_select_chapter ON event_organizers;
CREATE POLICY event_organizers_select_chapter ON event_organizers
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS event_audience_select_chapter ON event_audience_members;
CREATE POLICY event_audience_select_chapter ON event_audience_members
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

-- ── Seed the 5 default types for every existing chapter ───────────────────────
-- (Chapters created later are get-or-seeded by the events service layer.)

INSERT INTO event_types (chapter_id, name)
SELECT c.id, t.name
FROM chapters c
CROSS JOIN (VALUES
    ('Chapter Meeting'), ('Philanthropy'), ('Brotherhood'), ('Social'), ('Recruitment')
) AS t(name)
ON CONFLICT (chapter_id, lower(name)) DO NOTHING;

-- ── audit_logs action catalog extension ───────────────────────────────────────
-- Other domains extend the same CHECK concurrently, so rebuild it from the
-- CURRENT definition plus our actions instead of hardcoding the full list.

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY[
        'CREATE_EVENT',
        'UPDATE_EVENT',
        'SET_EVENT_SUPERVISOR',
        'ADD_EVENT_ORGANIZER',
        'REMOVE_EVENT_ORGANIZER'
    ];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        -- Format A: action = ANY (ARRAY['X'::text, 'Y'::text, ...])
        v_match := regexp_match(v_def, 'ARRAY\[(.+?)\]');
        IF v_match IS NOT NULL THEN
            FOREACH v_elem IN ARRAY string_to_array(v_match[1], ',') LOOP
                v_elem := trim(both '''' from regexp_replace(trim(v_elem), '::text$', ''));
                v_actions := v_actions || v_elem;
            END LOOP;
        ELSE
            -- Format B: action = ANY ('{X,Y,...}'::text[])
            v_match := regexp_match(v_def, '''(\{.+?\})''::text\[\]');
            IF v_match IS NOT NULL THEN
                v_actions := v_match[1]::text[];
            END IF;
        END IF;
    END IF;

    FOREACH v_elem IN ARRAY v_new LOOP
        IF NOT (v_elem = ANY (v_actions)) THEN
            v_actions := v_actions || v_elem;
        END IF;
    END LOOP;

    SELECT string_agg(quote_literal(a), ', ') INTO v_list FROM unnest(v_actions) AS a;

    EXECUTE 'ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check';
    EXECUTE 'ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check '
         || 'CHECK (action = ANY (ARRAY[' || v_list || ']::text[]))';
END $$;
