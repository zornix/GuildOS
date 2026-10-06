-- F-060 / D5: event and initiative clocks are local to the chapter.
CREATE OR REPLACE FUNCTION ev_local_start(p_chapter_id UUID, p_date DATE, p_time TIME)
RETURNS TIMESTAMPTZ
LANGUAGE sql STABLE AS $$
    SELECT (p_date + COALESCE(p_time, TIME '00:00'))
           AT TIME ZONE (SELECT timezone FROM chapters WHERE id = p_chapter_id);
$$;
REVOKE ALL ON FUNCTION ev_local_start(UUID, DATE, TIME) FROM PUBLIC;

CREATE OR REPLACE FUNCTION tk_uncommit_task(
    p_chapter_id UUID,
    p_task_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_reason TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_commitment task_commitments%ROWTYPE;
    v_event_start TIMESTAMPTZ;
    v_hours NUMERIC;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_uncommit_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    SELECT * INTO v_commitment FROM task_commitments
     WHERE task_id = p_task_id AND member_id = p_member_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % has no active commitment on task %', p_member_id, p_task_id;
    END IF;

    -- Security assignments cannot be unclaimed (D12); the swap flow is the only
    -- way the holder changes.
    IF v_task.kind = 'security' THEN
        RAISE EXCEPTION 'security_no_unclaim';
    END IF;

    IF v_task.event_id IS NOT NULL THEN
        SELECT ev_local_start(p_chapter_id, e.date, e.time)
          INTO v_event_start
          FROM events e WHERE e.id = v_task.event_id;
        v_hours := ROUND((EXTRACT(EPOCH FROM (v_event_start - now())) / 3600.0)::numeric, 2);
    END IF;

    IF v_task.initiative_id IS NOT NULL THEN
        SELECT ev_local_start(p_chapter_id, i.date, i.time)
          INTO v_event_start
          FROM initiatives i WHERE i.id = v_task.initiative_id;
        v_hours := ROUND((EXTRACT(EPOCH FROM (v_event_start - now())) / 3600.0)::numeric, 2);
    END IF;

    -- Hard lock (decision D2): unclaiming is blocked inside T-36h of event/initiative start.
    IF v_event_start IS NOT NULL AND v_event_start - now() < interval '36 hours' THEN
        RAISE EXCEPTION 'unclaim_locked';
    END IF;

    UPDATE task_commitments
       SET status = 'uncommitted', uncommitted_at = now()
     WHERE id = v_commitment.id
    RETURNING * INTO v_commitment;

    INSERT INTO task_commitment_log
        (chapter_id, task_id, member_id, action, late, reason, event_id, hours_before_event)
    VALUES
        (p_chapter_id, p_task_id, p_member_id, 'uncommit', FALSE, p_reason,
         v_task.event_id, v_hours);

    -- Last active claimant leaving reverts an in-progress job to open.
    IF v_task.status = 'in_progress'
       AND NOT EXISTS (SELECT 1 FROM task_commitments
                        WHERE task_id = p_task_id AND status = 'active') THEN
        UPDATE tasks SET status = 'open', updated_at = now()
         WHERE id = p_task_id
        RETURNING * INTO v_task;
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UNCOMMIT_TASK', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('member_id', p_member_id, 'commitment_id', v_commitment.id,
                               'hours_before_event', v_hours, 'reason', p_reason));

    v_result := jsonb_build_object(
        'commitment', to_jsonb(v_commitment),
        'task_status', v_task.status,
        'hours_before_event', v_hours
    );

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_uncommit_task', p_idempotency_key, v_commitment.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
