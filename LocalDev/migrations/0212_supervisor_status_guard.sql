-- Apply D12 to supervisors and avoid blocking unrelated initiative child inserts.

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

    -- The creator becomes a supervisor and must be eligible to participate.
    IF p_actor_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = p_actor_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', p_actor_id;
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
    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', p_member_id;
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

CREATE OR REPLACE FUNCTION in_add_chair(
    p_chapter_id UUID,
    p_initiative_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row initiative_chairs%ROWTYPE;
    v_result JSONB;
BEGIN
    -- Serialize chair changes per initiative so the last-chair count cannot be raced (F-047).
    PERFORM 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id FOR NO KEY UPDATE;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'in_add_chair' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'initiative % is not in chapter %', p_initiative_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM initiative_chairs
         WHERE initiative_id = p_initiative_id AND member_id = p_actor_id
    ) THEN
        RAISE EXCEPTION 'not_assigned_chair';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member_not_in_chapter';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', p_member_id;
    END IF;

    INSERT INTO initiative_chairs (chapter_id, initiative_id, member_id, is_creator, added_by)
    VALUES (p_chapter_id, p_initiative_id, p_member_id, FALSE, p_actor_id)
    ON CONFLICT (initiative_id, member_id) DO NOTHING
    RETURNING * INTO v_row;

    IF v_row.id IS NULL THEN
        -- Already a chair: idempotent success, return the existing row.
        SELECT * INTO v_row FROM initiative_chairs
         WHERE initiative_id = p_initiative_id AND member_id = p_member_id;
    ELSE
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'INITIATIVE_CHAIR_ADDED', p_actor_id, 'initiatives', p_initiative_id,
                jsonb_build_object('member_id', p_member_id, 'chair_id', v_row.id));
    END IF;

    v_result := to_jsonb(v_row);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'in_add_chair', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION in_remove_chair(
    p_chapter_id UUID,
    p_initiative_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row initiative_chairs%ROWTYPE;
    v_remaining INT;
    v_result JSONB;
BEGIN
    -- Serialize chair changes per initiative so the last-chair count cannot be raced (F-047).
    PERFORM 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id FOR NO KEY UPDATE;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'in_remove_chair' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'initiative % is not in chapter %', p_initiative_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM initiative_chairs
         WHERE initiative_id = p_initiative_id AND member_id = p_actor_id
    ) THEN
        RAISE EXCEPTION 'not_assigned_chair';
    END IF;

    SELECT * INTO v_row FROM initiative_chairs
     WHERE initiative_id = p_initiative_id AND member_id = p_member_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % is not a chair of initiative %', p_member_id, p_initiative_id;
    END IF;

    SELECT count(*) INTO v_remaining FROM initiative_chairs WHERE initiative_id = p_initiative_id;
    IF v_remaining <= 1 THEN
        RAISE EXCEPTION 'last_chair';
    END IF;

    DELETE FROM initiative_chairs WHERE id = v_row.id;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'INITIATIVE_CHAIR_REMOVED', p_actor_id, 'initiatives', p_initiative_id,
            jsonb_build_object('member_id', p_member_id, 'chair_id', v_row.id));

    v_result := jsonb_build_object('removed', TRUE, 'initiative_id', p_initiative_id, 'member_id', p_member_id);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'in_remove_chair', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
