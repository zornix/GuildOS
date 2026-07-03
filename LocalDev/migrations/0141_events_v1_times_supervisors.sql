-- Events V1 Phase 1 — end times, invite link, and co-supervisors.
-- Spec §2.1. Additive: legacy columns (single supervisor_member_id) are left in
-- place and deprecated (see api/events/CONFORM_TODO.md); all reads move to the
-- new event_supervisors join table.
--
-- Follows the append-only migration rule: this file redefines ev_create_event
-- (the 0101 definition is untouched) and adds two new supervisor RPCs.

-- ── 1. Events columns: end time + invite link ────────────────────────────────
-- Nullable on purpose (legacy rows have no end time). end > start is validated in
-- the service layer, not by a DB CHECK, because end_date defaults to date.

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS end_date    DATE,
    ADD COLUMN IF NOT EXISTS end_time    TIME,
    ADD COLUMN IF NOT EXISTS invite_link TEXT;

-- ── 2. event_supervisors (co-supervisors; creator locked in, min-1 invariant) ─
-- Same shape as event_organizers (0100): chapter-scoped, RLS select policy via
-- rbac_request_chapter_id(), writes go through the ev_* service-role RPCs.

CREATE TABLE IF NOT EXISTS event_supervisors (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id   UUID NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    member_id  UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    is_creator BOOLEAN NOT NULL DEFAULT FALSE,
    added_by   UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_supervisors UNIQUE (event_id, member_id)
);

CREATE INDEX IF NOT EXISTS ix_event_supervisors_chapter_id ON event_supervisors(chapter_id);
CREATE INDEX IF NOT EXISTS ix_event_supervisors_event_id   ON event_supervisors(event_id);
CREATE INDEX IF NOT EXISTS ix_event_supervisors_member_id  ON event_supervisors(member_id);

ALTER TABLE event_supervisors ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_supervisors_select_chapter ON event_supervisors;
CREATE POLICY event_supervisors_select_chapter ON event_supervisors
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

-- ── 3. Backfill (idempotent) ─────────────────────────────────────────────────
-- The creator is always a supervisor (spec §2.1); the creator row wins is_creator.
INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
SELECT e.chapter_id, e.id, e.created_by, TRUE
  FROM events e WHERE e.created_by IS NOT NULL
ON CONFLICT (event_id, member_id) DO NOTHING;

-- The existing single supervisor becomes a co-supervisor (unless already the
-- creator, in which case the is_creator=TRUE row above wins via ON CONFLICT).
INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
SELECT e.chapter_id, e.id, e.supervisor_member_id, FALSE
  FROM events e WHERE e.supervisor_member_id IS NOT NULL
ON CONFLICT (event_id, member_id) DO NOTHING;

-- ── 4. ev_create_event — new end/invite params + creator supervisor row ───────
-- Adding parameters changes the function identity, so DROP the 0101 signature
-- then CREATE the new one. New params are appended with DEFAULT NULL so existing
-- positional callers keep working (the service calls by name).
DROP FUNCTION IF EXISTS ev_create_event(
    UUID, TEXT, TEXT, DATE, TIME, TEXT, BOOLEAN, BOOLEAN, NUMERIC, TEXT, UUID,
    TEXT, UUID, UUID, JSONB, UUID, TEXT
);

CREATE OR REPLACE FUNCTION ev_create_event(
    p_chapter_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_date DATE,
    p_time TIME,
    p_location TEXT,
    p_required BOOLEAN,
    p_finable BOOLEAN,
    p_fine_amount NUMERIC,
    p_event_type TEXT,
    p_event_type_id UUID,
    p_visibility TEXT,
    p_event_group_id UUID,
    p_group_with_event_id UUID,
    p_audience_member_ids JSONB,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL,
    p_end_date DATE DEFAULT NULL,
    p_end_time TIME DEFAULT NULL,
    p_invite_link TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_group_id UUID := p_event_group_id;
    v_event events%ROWTYPE;
    v_member_id UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_create_event' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- Tenant guards
    IF p_event_type_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM event_types WHERE id = p_event_type_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event type % is not in chapter %', p_event_type_id, p_chapter_id;
    END IF;
    IF v_group_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM event_groups WHERE id = v_group_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event group % is not in chapter %', v_group_id, p_chapter_id;
    END IF;

    -- Get-or-create the group shared with another event.
    IF v_group_id IS NULL AND p_group_with_event_id IS NOT NULL THEN
        SELECT event_group_id INTO v_group_id
          FROM events WHERE id = p_group_with_event_id AND chapter_id = p_chapter_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'event % is not in chapter %', p_group_with_event_id, p_chapter_id;
        END IF;
        IF v_group_id IS NULL THEN
            INSERT INTO event_groups (chapter_id, created_by)
            VALUES (p_chapter_id, p_actor_id)
            RETURNING id INTO v_group_id;
            UPDATE events SET event_group_id = v_group_id WHERE id = p_group_with_event_id;
        END IF;
    END IF;

    INSERT INTO events (chapter_id, title, description, date, time, end_date, end_time,
                        invite_link, location, required, finable, fine_amount, event_type,
                        event_type_id, visibility, event_group_id, created_by)
    VALUES (p_chapter_id, p_title, p_description, p_date, p_time, p_end_date, p_end_time,
            p_invite_link, p_location,
            COALESCE(p_required, FALSE), COALESCE(p_finable, FALSE),
            COALESCE(p_fine_amount, 0), p_event_type, p_event_type_id,
            COALESCE(p_visibility, 'chapter'), v_group_id, p_actor_id)
    RETURNING * INTO v_event;

    -- The creator is always a supervisor (spec §2.1).
    IF p_actor_id IS NOT NULL THEN
        INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator, added_by)
        VALUES (p_chapter_id, v_event.id, p_actor_id, TRUE, p_actor_id)
        ON CONFLICT (event_id, member_id) DO NOTHING;
    END IF;

    IF COALESCE(p_visibility, 'chapter') = 'custom' AND p_audience_member_ids IS NOT NULL THEN
        FOR v_member_id IN
            SELECT value::uuid FROM jsonb_array_elements_text(p_audience_member_ids)
        LOOP
            IF NOT EXISTS (SELECT 1 FROM members WHERE id = v_member_id AND chapter_id = p_chapter_id) THEN
                RAISE EXCEPTION 'audience member % is not in chapter %', v_member_id, p_chapter_id;
            END IF;
            INSERT INTO event_audience_members (chapter_id, event_id, member_id)
            VALUES (p_chapter_id, v_event.id, v_member_id)
            ON CONFLICT (event_id, member_id) DO NOTHING;
        END LOOP;
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_EVENT', p_actor_id, 'events', v_event.id,
            jsonb_build_object('title', p_title, 'visibility', v_event.visibility,
                               'event_group_id', v_group_id, 'finable', v_event.finable,
                               'required', v_event.required));

    v_result := to_jsonb(v_event);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_create_event', p_idempotency_key, v_event.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 5. ev_add_supervisor — add a co-supervisor ───────────────────────────────
-- Eligibility (officer/chair role keys) is passed in by the service layer, which
-- owns the canonical list; the RPC re-checks as defense in depth. Idempotent add.

CREATE OR REPLACE FUNCTION ev_add_supervisor(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_required_role_keys JSONB,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row event_supervisors%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_add_supervisor' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;
    IF p_required_role_keys IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM member_roles
         WHERE chapter_id = p_chapter_id AND member_id = p_member_id
           AND role_key IN (SELECT value FROM jsonb_array_elements_text(p_required_role_keys))
    ) THEN
        RAISE EXCEPTION 'member % does not hold an eligible supervisor role', p_member_id;
    END IF;

    INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator, added_by)
    VALUES (p_chapter_id, p_event_id, p_member_id, FALSE, p_actor_id)
    ON CONFLICT (event_id, member_id) DO NOTHING
    RETURNING * INTO v_row;

    IF v_row.id IS NULL THEN
        -- Already a supervisor: idempotent success, return the existing row.
        SELECT * INTO v_row FROM event_supervisors
         WHERE event_id = p_event_id AND member_id = p_member_id;
    ELSE
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'ADD_EVENT_SUPERVISOR', p_actor_id, 'events', p_event_id,
                jsonb_build_object('member_id', p_member_id, 'supervisor_id', v_row.id));
    END IF;

    v_result := to_jsonb(v_row);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_add_supervisor', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 6. ev_remove_supervisor — remove a co-supervisor (min-1, creator locked) ──

CREATE OR REPLACE FUNCTION ev_remove_supervisor(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row event_supervisors%ROWTYPE;
    v_remaining INT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_remove_supervisor' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;

    SELECT * INTO v_row FROM event_supervisors
     WHERE event_id = p_event_id AND member_id = p_member_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % is not a supervisor of event %', p_member_id, p_event_id;
    END IF;

    IF v_row.is_creator THEN
        RAISE EXCEPTION 'creator_supervisor_locked';
    END IF;

    SELECT count(*) INTO v_remaining FROM event_supervisors WHERE event_id = p_event_id;
    IF v_remaining <= 1 THEN
        -- Belt-and-braces: the creator row is locked above, so this is unreachable
        -- in practice, but the min-1 invariant is enforced regardless.
        RAISE EXCEPTION 'last_supervisor_locked';
    END IF;

    DELETE FROM event_supervisors WHERE id = v_row.id;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'REMOVE_EVENT_SUPERVISOR', p_actor_id, 'events', p_event_id,
            jsonb_build_object('member_id', p_member_id, 'supervisor_id', v_row.id));

    v_result := jsonb_build_object('removed', TRUE, 'event_id', p_event_id, 'member_id', p_member_id);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_remove_supervisor', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 7. audit_logs action catalog extension (additive, concurrent-safe) ────────
-- Rebuild from the live definition (other domains extend the same CHECK). The
-- verb-first names match the existing ADD_/REMOVE_EVENT_ORGANIZER style (0101).
-- pg_get_constraintdef may render the list as ARRAY['X'::text, ...] (Format A)
-- or '{X,Y,...}'::text[] (Format B) depending on which migration last rebuilt
-- it — handle both (template at 0100:117-164).

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['ADD_EVENT_SUPERVISOR', 'REMOVE_EVENT_SUPERVISOR'];
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
