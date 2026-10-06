-- Complete the security swap lock and initiative creation status guards.

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
    -- Serialize with assignments and other accepts before reading commitments.
    PERFORM pg_advisory_xact_lock(hashtext('ev_security:' || v_swap.event_id::text));

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

CREATE OR REPLACE FUNCTION in_create_initiative(
    p_chapter_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_date DATE,
    p_time TIME,
    p_end_date DATE,
    p_end_time TIME,
    p_chair_member_ids UUID[],
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_initiative initiatives%ROWTYPE;
    v_chair_ids UUID[];
    v_chair_id UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'in_create_initiative' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    v_chair_ids := COALESCE(p_chair_member_ids, ARRAY[]::UUID[]);
    IF p_actor_id IS NOT NULL AND NOT (p_actor_id = ANY (v_chair_ids)) THEN
        v_chair_ids := v_chair_ids || p_actor_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM unnest(v_chair_ids) AS c(member_id)
        LEFT JOIN members m ON m.id = c.member_id AND m.chapter_id = p_chapter_id
        WHERE m.id IS NULL
    ) THEN
        RAISE EXCEPTION 'member_not_in_chapter';
    END IF;

    FOREACH v_chair_id IN ARRAY v_chair_ids LOOP
        IF NOT EXISTS (
            SELECT 1 FROM members
             WHERE id = v_chair_id AND chapter_id = p_chapter_id AND status IN ('active', 'invited')
        ) THEN
            RAISE EXCEPTION 'member % is not an active member', v_chair_id;
        END IF;
    END LOOP;

    INSERT INTO initiatives (chapter_id, title, description, date, time, end_date, end_time, created_by)
    VALUES (p_chapter_id, p_title, p_description, p_date, p_time, p_end_date, p_end_time, p_actor_id)
    RETURNING * INTO v_initiative;

    FOREACH v_chair_id IN ARRAY v_chair_ids LOOP
        INSERT INTO initiative_chairs (chapter_id, initiative_id, member_id, is_creator, added_by)
        VALUES (p_chapter_id, v_initiative.id, v_chair_id, (v_chair_id = p_actor_id), p_actor_id)
        ON CONFLICT (initiative_id, member_id) DO NOTHING;
    END LOOP;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'INITIATIVE_CREATED', p_actor_id, 'initiatives', v_initiative.id,
            jsonb_build_object('title', p_title, 'chair_member_ids', to_jsonb(v_chair_ids)));

    v_result := to_jsonb(v_initiative) || jsonb_build_object('chair_member_ids', to_jsonb(v_chair_ids));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'in_create_initiative', p_idempotency_key, v_initiative.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
