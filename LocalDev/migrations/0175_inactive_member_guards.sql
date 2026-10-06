-- F-054: refuse to assign inactive or alumni members. invited stays assignable (D12).
-- 0172 and 0174 are already applied, so the live bodies (including their locks)
-- are copied here and only the status predicate is added.

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

    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', p_member_id;
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

CREATE OR REPLACE FUNCTION ev_request_security_swap(
    p_chapter_id UUID,
    p_task_id UUID,
    p_target_member_id UUID,
    p_actor_id UUID,
    p_note TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_swap security_swap_requests%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_request_security_swap' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;
    IF v_task.kind <> 'security' OR v_task.status <> 'in_progress' THEN
        RAISE EXCEPTION 'swap_wrong_state';
    END IF;

    -- Only the current holder (active commitment) may request a swap.
    IF NOT EXISTS (SELECT 1 FROM task_commitments
                    WHERE task_id = p_task_id AND member_id = p_actor_id AND status = 'active') THEN
        RAISE EXCEPTION 'not_assigned';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_target_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_target_member_id, p_chapter_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = p_target_member_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', p_target_member_id;
    END IF;

    IF p_target_member_id = p_actor_id THEN
        RAISE EXCEPTION 'swap_self';
    END IF;

    -- Target must not already be actively assigned to security on the same event.
    IF EXISTS (
        SELECT 1 FROM tasks t
          JOIN task_commitments tc ON tc.task_id = t.id AND tc.status = 'active'
         WHERE t.event_id = v_task.event_id AND t.chapter_id = p_chapter_id
           AND t.kind = 'security' AND tc.member_id = p_target_member_id
    ) THEN
        RAISE EXCEPTION 'target_already_assigned';
    END IF;

    BEGIN
        INSERT INTO security_swap_requests
            (chapter_id, event_id, task_id, requester_member_id, target_member_id, note, status)
        VALUES
            (p_chapter_id, v_task.event_id, p_task_id, p_actor_id, p_target_member_id, p_note, 'pending')
        RETURNING * INTO v_swap;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'swap_already_pending';
    END;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_SWAP_REQUESTED', p_actor_id,
            'security_swap_requests', v_swap.id,
            jsonb_build_object('task_id', p_task_id, 'event_id', v_task.event_id,
                               'target_member_id', p_target_member_id));

    INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                dedup_key, payload, status)
    VALUES (p_chapter_id, 'SECURITY_SWAP_REQUESTED', p_target_member_id,
            'security_swap_requests', v_swap.id,
            'security_swap_requested:' || v_swap.id || ':' || p_target_member_id,
            jsonb_build_object('swap_id', v_swap.id, 'task_id', p_task_id,
                               'event_id', v_task.event_id,
                               'requester_member_id', p_actor_id, 'note', p_note),
            'pending')
    ON CONFLICT (dedup_key) DO NOTHING;

    v_result := to_jsonb(v_swap);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_request_security_swap', p_idempotency_key, v_swap.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION ev_accept_security_swap(
    p_chapter_id UUID,
    p_swap_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_swap security_swap_requests%ROWTYPE;
    v_task tasks%ROWTYPE;
    v_req_commitment task_commitments%ROWTYPE;
    v_new_commitment task_commitments%ROWTYPE;
    v_member UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_accept_security_swap' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_swap FROM security_swap_requests
     WHERE id = p_swap_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'swap % not found in chapter %', p_swap_id, p_chapter_id;
    END IF;
    IF v_swap.status <> 'pending' THEN
        RAISE EXCEPTION 'swap_wrong_state';
    END IF;
    IF p_actor_id <> v_swap.target_member_id THEN
        RAISE EXCEPTION 'not_swap_target';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM members
         WHERE id = v_swap.target_member_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'member % is not an active member', v_swap.target_member_id;
    END IF;

    -- Serialize with racing claims/swaps on the same assignment.
    SELECT * INTO v_task FROM tasks
     WHERE id = v_swap.task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', v_swap.task_id, p_chapter_id;
    END IF;
    IF v_task.kind <> 'security' OR v_task.status <> 'in_progress' THEN
        RAISE EXCEPTION 'swap_wrong_state';
    END IF;

    -- Requester's commitment must still be active (else the assignment moved).
    SELECT * INTO v_req_commitment FROM task_commitments
     WHERE task_id = v_swap.task_id AND member_id = v_swap.requester_member_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'swap_stale';
    END IF;

    -- Target still not otherwise assigned to security on the event.
    IF EXISTS (
        SELECT 1 FROM tasks t
          JOIN task_commitments tc ON tc.task_id = t.id AND tc.status = 'active'
         WHERE t.event_id = v_task.event_id AND t.chapter_id = p_chapter_id
           AND t.kind = 'security' AND tc.member_id = v_swap.target_member_id
    ) THEN
        RAISE EXCEPTION 'target_already_assigned';
    END IF;

    -- Flip the commitment atomically: uncommit requester, commit target.
    UPDATE task_commitments
       SET status = 'uncommitted', uncommitted_at = now()
     WHERE id = v_req_commitment.id;

    INSERT INTO task_commitment_log
        (chapter_id, task_id, member_id, action, late, reason, event_id)
    VALUES
        (p_chapter_id, v_swap.task_id, v_swap.requester_member_id, 'uncommit', FALSE,
         'security_swap', v_task.event_id);

    INSERT INTO task_commitments (chapter_id, task_id, member_id, status)
    VALUES (p_chapter_id, v_swap.task_id, v_swap.target_member_id, 'active')
    RETURNING * INTO v_new_commitment;

    INSERT INTO task_commitment_log
        (chapter_id, task_id, member_id, action, late, event_id)
    VALUES
        (p_chapter_id, v_swap.task_id, v_swap.target_member_id, 'commit', FALSE, v_task.event_id);

    UPDATE security_swap_requests
       SET status = 'accepted', resolved_at = now(), resolved_by = p_actor_id
     WHERE id = p_swap_id
    RETURNING * INTO v_swap;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_SWAP_ACCEPTED', p_actor_id,
            'security_swap_requests', v_swap.id,
            jsonb_build_object('task_id', v_swap.task_id, 'event_id', v_task.event_id,
                               'requester_member_id', v_swap.requester_member_id,
                               'target_member_id', v_swap.target_member_id));

    -- Outbox to requester + target + every event supervisor (spec §2.7).
    -- UNION dedups when a party is also a supervisor.
    FOR v_member IN
        SELECT v_swap.requester_member_id
        UNION
        SELECT v_swap.target_member_id
        UNION
        SELECT member_id FROM event_supervisors WHERE event_id = v_task.event_id
    LOOP
        INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                    dedup_key, payload, status)
        VALUES (p_chapter_id, 'SECURITY_SWAP_ACCEPTED', v_member,
                'security_swap_requests', v_swap.id,
                'security_swap_accepted:' || v_swap.id || ':' || v_member,
                jsonb_build_object('swap_id', v_swap.id, 'task_id', v_swap.task_id,
                                   'event_id', v_task.event_id,
                                   'requester_member_id', v_swap.requester_member_id,
                                   'target_member_id', v_swap.target_member_id),
                'pending')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    v_result := to_jsonb(v_swap);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_accept_security_swap', p_idempotency_key, v_swap.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION tk_commit_task(
    p_chapter_id UUID,
    p_task_id UUID,
    p_member_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_active_count INT;
    v_commitment task_commitments%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_commit_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- Lock the task row first to serialize racing claims against the capacity check.
    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    -- Security assignments are pre-assigned (D12); the swap flow is the only
    -- way the holder changes.
    IF v_task.kind = 'security' THEN
        RAISE EXCEPTION 'security_preassigned';
    END IF;

    IF v_task.status IN ('done', 'cancelled', 'done_reported', 'approved') THEN
        RAISE EXCEPTION 'task % is %, it cannot be committed to', p_task_id, v_task.status;
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

    IF EXISTS (SELECT 1 FROM task_commitments
                WHERE task_id = p_task_id AND member_id = p_member_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % already has an active commitment on task %', p_member_id, p_task_id;
    END IF;

    -- Capacity: the task row lock above serializes concurrent claims.
    SELECT count(*) INTO v_active_count FROM task_commitments
     WHERE task_id = p_task_id AND status = 'active';
    IF v_active_count >= v_task.people_needed THEN
        RAISE EXCEPTION 'job_full';
    END IF;

    INSERT INTO task_commitments (chapter_id, task_id, member_id, status)
    VALUES (p_chapter_id, p_task_id, p_member_id, 'active')
    RETURNING * INTO v_commitment;

    INSERT INTO task_commitment_log (chapter_id, task_id, member_id, action, late, event_id)
    VALUES (p_chapter_id, p_task_id, p_member_id, 'commit', FALSE, v_task.event_id);

    -- First active claim on an open job starts progress (🔴 → 🟢).
    IF v_task.status = 'open' THEN
        UPDATE tasks SET status = 'in_progress', updated_at = now()
         WHERE id = p_task_id
        RETURNING * INTO v_task;
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'COMMIT_TASK', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('member_id', p_member_id, 'commitment_id', v_commitment.id));

    v_result := jsonb_build_object(
        'commitment', to_jsonb(v_commitment),
        'task_status', v_task.status
    );

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_commit_task', p_idempotency_key, v_commitment.id, v_result);
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
