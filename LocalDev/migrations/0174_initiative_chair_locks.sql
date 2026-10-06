-- F-047: lock the parent initiative before chair add/remove so the last-chair
-- count cannot be raced. 0172 is already applied, so this is a new file.

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
    PERFORM 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id FOR UPDATE;

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
    PERFORM 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id FOR UPDATE;

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
