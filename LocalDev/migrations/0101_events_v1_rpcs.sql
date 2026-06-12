-- Events V1 RPCs — multi-row trust-boundary mutations (pattern: 0083/0085).
-- Every function: chapter tenant guards, idempotency via idempotency_keys
-- (where keys are supplied), and audit_logs writes.
--
-- Array-ish params are JSONB (the postgres shim and supabase-py both serialize
-- Python lists as JSON).

-- ── ev_create_event ────────────────────────────────────────────────────────────
-- Creates the event plus its custom-audience rows and (optionally) gets/creates
-- the event group shared with another event — one transaction.

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
    p_idempotency_key TEXT DEFAULT NULL
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

    INSERT INTO events (chapter_id, title, description, date, time, location,
                        required, finable, fine_amount, event_type, event_type_id,
                        visibility, event_group_id, created_by)
    VALUES (p_chapter_id, p_title, p_description, p_date, p_time, p_location,
            COALESCE(p_required, FALSE), COALESCE(p_finable, FALSE),
            COALESCE(p_fine_amount, 0), p_event_type, p_event_type_id,
            COALESCE(p_visibility, 'chapter'), v_group_id, p_actor_id)
    RETURNING * INTO v_event;

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

-- ── ev_set_audience ────────────────────────────────────────────────────────────
-- Replaces the custom audience list (used by event update).

CREATE OR REPLACE FUNCTION ev_set_audience(
    p_chapter_id UUID,
    p_event_id UUID,
    p_audience_member_ids JSONB,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_member_id UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_set_audience' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;

    DELETE FROM event_audience_members WHERE event_id = p_event_id;

    FOR v_member_id IN
        SELECT value::uuid FROM jsonb_array_elements_text(COALESCE(p_audience_member_ids, '[]'::jsonb))
    LOOP
        IF NOT EXISTS (SELECT 1 FROM members WHERE id = v_member_id AND chapter_id = p_chapter_id) THEN
            RAISE EXCEPTION 'audience member % is not in chapter %', v_member_id, p_chapter_id;
        END IF;
        INSERT INTO event_audience_members (chapter_id, event_id, member_id)
        VALUES (p_chapter_id, p_event_id, v_member_id)
        ON CONFLICT (event_id, member_id) DO NOTHING;
    END LOOP;

    UPDATE events SET visibility = 'custom' WHERE id = p_event_id;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UPDATE_EVENT', p_actor_id, 'events', p_event_id,
            jsonb_build_object('audience_member_ids', COALESCE(p_audience_member_ids, '[]'::jsonb)));

    v_result := jsonb_build_object('event_id', p_event_id,
                                   'audience_member_ids', COALESCE(p_audience_member_ids, '[]'::jsonb));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_set_audience', p_idempotency_key, p_event_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── ev_set_supervisor ──────────────────────────────────────────────────────────
-- Sets/replaces the single supervisor. The eligible role keys are passed in by
-- the service layer (CHAIR_ROLES in api/events/auth.py) so the constant lives
-- in exactly one place; the function re-checks them as defense in depth.

CREATE OR REPLACE FUNCTION ev_set_supervisor(
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
    v_event events%ROWTYPE;
    v_previous UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_set_supervisor' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_event FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
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

    v_previous := v_event.supervisor_member_id;

    UPDATE events SET supervisor_member_id = p_member_id
     WHERE id = p_event_id
    RETURNING * INTO v_event;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SET_EVENT_SUPERVISOR', p_actor_id, 'events', p_event_id,
            jsonb_build_object('supervisor_member_id', p_member_id,
                               'previous_supervisor_member_id', v_previous));

    v_result := to_jsonb(v_event);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_set_supervisor', p_idempotency_key, p_event_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── ev_add_organizer ───────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION ev_add_organizer(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_source TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row event_organizers%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_add_organizer' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    INSERT INTO event_organizers (chapter_id, event_id, member_id, source)
    VALUES (p_chapter_id, p_event_id, p_member_id, COALESCE(p_source, 'volunteer'))
    ON CONFLICT (event_id, member_id) DO NOTHING
    RETURNING * INTO v_row;

    IF v_row.id IS NULL THEN
        -- Already an organizer: idempotent success, return the existing row.
        SELECT * INTO v_row FROM event_organizers
         WHERE event_id = p_event_id AND member_id = p_member_id;
    ELSE
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'ADD_EVENT_ORGANIZER', p_actor_id, 'events', p_event_id,
                jsonb_build_object('member_id', p_member_id, 'source', v_row.source,
                                   'organizer_id', v_row.id));
    END IF;

    v_result := to_jsonb(v_row);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_add_organizer', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── ev_remove_organizer ────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION ev_remove_organizer(
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
    v_row event_organizers%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_remove_organizer' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;

    DELETE FROM event_organizers
     WHERE event_id = p_event_id AND member_id = p_member_id AND chapter_id = p_chapter_id
    RETURNING * INTO v_row;

    IF v_row.id IS NOT NULL THEN
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'REMOVE_EVENT_ORGANIZER', p_actor_id, 'events', p_event_id,
                jsonb_build_object('member_id', p_member_id, 'organizer_id', v_row.id));
    END IF;

    v_result := jsonb_build_object('removed', v_row.id IS NOT NULL,
                                   'event_id', p_event_id, 'member_id', p_member_id);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_remove_organizer', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
