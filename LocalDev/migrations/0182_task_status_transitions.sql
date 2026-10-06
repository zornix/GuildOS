-- Keep idempotent replay ahead of lifecycle validation.
CREATE OR REPLACE FUNCTION tk_update_task_status(
    p_chapter_id UUID,
    p_task_id UUID,
    p_status TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_old_status TEXT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_update_task_status' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_status IN ('done_reported', 'approved') THEN
        RAISE EXCEPTION 'status % is set only via the job report/approve RPCs', p_status;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    -- Security roster changes go only through the ev_* security RPCs (D12).
    IF v_task.kind = 'security' THEN
        RAISE EXCEPTION 'security_no_status_change';
    END IF;

    v_old_status := v_task.status;
    IF v_old_status IN ('approved', 'cancelled') THEN
        RAISE EXCEPTION 'task_closed: a % task cannot change status', v_old_status;
    END IF;
    IF v_old_status = 'done_reported' THEN
        RAISE EXCEPTION 'task_in_review: approve or reject the reported job instead';
    END IF;
    IF p_status = 'done' AND (v_task.event_id IS NOT NULL OR v_task.initiative_id IS NOT NULL) THEN
        RAISE EXCEPTION 'job_needs_review: jobs are completed through report and approve';
    END IF;

    UPDATE tasks SET status = p_status, updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    IF p_status = 'done' AND v_old_status <> 'done' THEN
        UPDATE task_commitments
           SET status = 'completed'
         WHERE task_id = p_task_id AND status = 'active';
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UPDATE_TASK_STATUS', p_actor_id, 'tasks', v_task.id,
            jsonb_build_object('status', p_status));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_update_task_status', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
