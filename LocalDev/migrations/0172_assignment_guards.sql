-- F-042: serialize security assignment per event so the duplicate pre-check
-- cannot be raced.

CREATE OR REPLACE FUNCTION ev_assign_security(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_title TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_event events%ROWTYPE;
    v_task tasks%ROWTYPE;
    v_commitment task_commitments%ROWTYPE;
    v_result JSONB;
BEGIN
    -- One assignment at a time per event, so the duplicate pre-check below cannot be raced (F-042).
    PERFORM pg_advisory_xact_lock(hashtext('ev_security:' || p_event_id::text));

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_assign_security' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_event FROM events
     WHERE id = p_event_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    -- Member must not already hold an active security assignment on this event.
    IF EXISTS (
        SELECT 1 FROM tasks t
          JOIN task_commitments tc ON tc.task_id = t.id AND tc.status = 'active'
         WHERE t.event_id = p_event_id AND t.chapter_id = p_chapter_id
           AND t.kind = 'security' AND tc.member_id = p_member_id
    ) THEN
        RAISE EXCEPTION 'target_already_assigned';
    END IF;

    INSERT INTO tasks (chapter_id, event_id, title, kind, status, people_needed,
                       created_by, required)
    VALUES (p_chapter_id, p_event_id, COALESCE(p_title, 'Security'), 'security',
            'in_progress', 1, p_actor_id, FALSE)
    RETURNING * INTO v_task;

    INSERT INTO task_commitments (chapter_id, task_id, member_id, status)
    VALUES (p_chapter_id, v_task.id, p_member_id, 'active')
    RETURNING * INTO v_commitment;

    INSERT INTO task_commitment_log (chapter_id, task_id, member_id, action, late, event_id)
    VALUES (p_chapter_id, v_task.id, p_member_id, 'commit', FALSE, p_event_id);

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_ASSIGNED', p_actor_id, 'tasks', v_task.id,
            jsonb_build_object('member_id', p_member_id, 'event_id', p_event_id,
                               'commitment_id', v_commitment.id));

    -- Neutral payload (task/event only) — never the Screen 6 delinquency score.
    INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                dedup_key, payload, status)
    VALUES (p_chapter_id, 'SECURITY_ASSIGNED', p_member_id, 'tasks', v_task.id,
            'security_assigned:' || v_task.id || ':' || p_member_id,
            jsonb_build_object('task_id', v_task.id, 'event_id', p_event_id,
                               'title', v_event.title, 'event_date', v_event.date),
            'pending')
    ON CONFLICT (dedup_key) DO NOTHING;

    v_result := jsonb_build_object('task', to_jsonb(v_task), 'commitment', to_jsonb(v_commitment));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_assign_security', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
