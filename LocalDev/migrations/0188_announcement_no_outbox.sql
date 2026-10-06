CREATE OR REPLACE FUNCTION an_send_announcement(
    p_chapter_id UUID,
    p_announcement_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_ann announcements%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'an_send_announcement' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_ann FROM announcements
     WHERE id = p_announcement_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'announcement % not found in chapter %', p_announcement_id, p_chapter_id;
    END IF;
    IF v_ann.status = 'sent' THEN
        RETURN to_jsonb(v_ann);  -- idempotent: already sent
    END IF;

    UPDATE announcements SET status = 'sent', sent_at = now(), updated_at = now()
     WHERE id = p_announcement_id
    RETURNING * INTO v_ann;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SEND_ANNOUNCEMENT', p_actor_id, 'announcements', v_ann.id,
            jsonb_build_object('audience', v_ann.audience));

    v_result := to_jsonb(v_ann);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'an_send_announcement', p_idempotency_key, v_ann.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
