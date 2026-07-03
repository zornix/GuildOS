-- Jobs V1 Phase 1 — the tasks domain becomes the spec's "jobs" (decision D1).
-- Storage/RPCs/routes stay tasks/tk_*; only the user-facing layer says "job".
--
-- Adds capacity (people_needed + fill state), the done_reported/approved states,
-- reject-with-required-reason, and the hard T-36h unclaim lock (decision D2).
-- Append-only migration rule: redefines the 0110 tk_* functions (0110 untouched)
-- and adds tk_report_done / tk_approve_task / tk_reject_task.

-- ── 1. tasks columns + status widening ───────────────────────────────────────
-- Spec-state mapping: 🔴 to-do = 'open', 🟢 in-progress = 'in_progress',
-- 🟡 done-reported = 'done_reported', ✅ = 'approved'. 'committed'/'done' stay
-- valid for legacy chore rows only; the job lifecycle never sets them.

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS people_needed    INT  NOT NULL DEFAULT 1
        CHECK (people_needed >= 1),
    ADD COLUMN IF NOT EXISTS reported_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS reported_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check CHECK (status IN
    ('open', 'committed', 'in_progress', 'done', 'cancelled',
     'done_reported', 'approved'));

-- ── 2. tk_commit_task — capacity guard + first-claim → in_progress ────────────
-- Same signature as 0110. Claiming stays open regardless of T-36h and through the
-- event (spec §2.4); only done_reported/approved/cancelled block it.

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

    IF v_task.status IN ('done', 'cancelled', 'done_reported', 'approved') THEN
        RAISE EXCEPTION 'task % is %, it cannot be committed to', p_task_id, v_task.status;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
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

-- ── 3. tk_uncommit_task — hard T-36h lock (replaces the 24h "late" flag) ──────
-- Standalone tasks (no event_id) are never locked. The append-only log keeps
-- writing hours_before_event; the `late` column is superseded but left in place.

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

    -- PHASE3 SEAM: the linked-event start is resolved here; initiatives will add a
    -- second parent type (resolve its start alongside v_task.event_id).
    IF v_task.event_id IS NOT NULL THEN
        SELECT (e.date + COALESCE(e.time, TIME '00:00'))::timestamptz
          INTO v_event_start
          FROM events e WHERE e.id = v_task.event_id;
        v_hours := ROUND((EXTRACT(EPOCH FROM (v_event_start - now())) / 3600.0)::numeric, 2);
    END IF;

    -- Hard lock (decision D2): unclaiming is blocked inside T-36h of event start.
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

    -- Last active claimant leaving reverts an in-progress job to 🔴 open.
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

-- ── 4. tk_update_task_status — refuse the job-lifecycle states ────────────────
-- done_reported/approved are only reachable via the dedicated RPCs below (they
-- carry claimant/approver guards and outbox fan-out). Same signature as 0110.

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
    v_old_status := v_task.status;

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

-- ── 5. tk_report_done — a claimant reports the job done (🟢 → 🟡) ─────────────
-- Guards: caller holds an active commitment; status must be 'in_progress' (this
-- enforces once-per-job — a second report finds 'done_reported' and raises
-- already_reported; an idempotency-key retry of the same report replays). Clears
-- any prior rejection banner (history stays in audit_logs). Enqueues JOB_REPORTED
-- to every event supervisor (the approvers).

CREATE OR REPLACE FUNCTION tk_report_done(
    p_chapter_id UUID,
    p_task_id UUID,
    p_member_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_cycle INT;
    v_approver UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_report_done' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM task_commitments
                    WHERE task_id = p_task_id AND member_id = p_member_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % has no active commitment on task %', p_member_id, p_task_id;
    END IF;

    IF v_task.status = 'done_reported' THEN
        RAISE EXCEPTION 'already_reported';
    END IF;
    IF v_task.status <> 'in_progress' THEN
        RAISE EXCEPTION 'task % is %, it cannot be reported done', p_task_id, v_task.status;
    END IF;

    UPDATE tasks
       SET status = 'done_reported', reported_by = p_member_id, reported_at = now(),
           rejected_by = NULL, rejected_at = NULL, rejection_reason = NULL,
           updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'JOB_REPORTED', p_member_id, 'tasks', p_task_id,
            jsonb_build_object('member_id', p_member_id));

    -- dedup_key is stable across idempotent retries and unique per rejection cycle.
    v_cycle := (SELECT count(*) FROM audit_logs
                 WHERE target_table = 'tasks' AND target_id = p_task_id AND action = 'JOB_REJECTED');

    -- One outbox row per approver (event supervisors). Standalone jobs (no event)
    -- have no supervisors here; their approval falls back to tasks:review holders.
    FOR v_approver IN
        SELECT member_id FROM event_supervisors WHERE event_id = v_task.event_id
    LOOP
        INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                    dedup_key, payload, status)
        VALUES (p_chapter_id, 'JOB_REPORTED', v_approver, 'tasks', p_task_id,
                'job_reported:' || p_task_id || ':' || v_cycle || ':' || v_approver,
                jsonb_build_object('task_id', p_task_id, 'reported_by', p_member_id,
                                   'title', v_task.title, 'event_id', v_task.event_id),
                'pending')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_report_done', p_idempotency_key, p_task_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 6. tk_approve_task — approver approves a reported job (🟡 → ✅) ────────────
-- The RPC enforces the state machine + tenancy; approver authorization is checked
-- in the Python service (can_approve_job). Marks active commitments completed and
-- enqueues JOB_APPROVED to every claimant.

CREATE OR REPLACE FUNCTION tk_approve_task(
    p_chapter_id UUID,
    p_task_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_claimant UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_approve_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    IF v_task.status <> 'done_reported' THEN
        RAISE EXCEPTION 'task % is %, it cannot be approved', p_task_id, v_task.status;
    END IF;

    -- Notify the claimants being credited before we flip them to completed.
    FOR v_claimant IN
        SELECT member_id FROM task_commitments
         WHERE task_id = p_task_id AND status = 'active'
    LOOP
        INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                    dedup_key, payload, status)
        VALUES (p_chapter_id, 'JOB_APPROVED', v_claimant, 'tasks', p_task_id,
                'job_approved:' || p_task_id || ':' || v_claimant,
                jsonb_build_object('task_id', p_task_id, 'approved_by', p_actor_id,
                                   'title', v_task.title, 'event_id', v_task.event_id),
                'pending')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    UPDATE task_commitments
       SET status = 'completed'
     WHERE task_id = p_task_id AND status = 'active';

    UPDATE tasks
       SET status = 'approved', approved_by = p_actor_id, approved_at = now(), updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'JOB_APPROVED', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('approved_by', p_actor_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_approve_task', p_idempotency_key, p_task_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 7. tk_reject_task — approver rejects a reported job (🟡 → 🟢/🔴) ──────────
-- Reason is required (rejected at the edge and here). Claimants are retained;
-- status returns to in_progress if any active commitments remain, else open.
-- Clears reported_*; enqueues JOB_REJECTED (with reason) to every claimant.

CREATE OR REPLACE FUNCTION tk_reject_task(
    p_chapter_id UUID,
    p_task_id UUID,
    p_actor_id UUID,
    p_reason TEXT,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_cycle INT;
    v_has_active BOOLEAN;
    v_claimant UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_reject_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_reason IS NULL OR length(btrim(p_reason)) = 0 THEN
        RAISE EXCEPTION 'rejection_reason_required';
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    IF v_task.status <> 'done_reported' THEN
        RAISE EXCEPTION 'task % is %, it cannot be rejected', p_task_id, v_task.status;
    END IF;

    -- Cycle counted before this rejection's own audit row (matches tk_report_done).
    v_cycle := (SELECT count(*) FROM audit_logs
                 WHERE target_table = 'tasks' AND target_id = p_task_id AND action = 'JOB_REJECTED');

    SELECT EXISTS (SELECT 1 FROM task_commitments
                    WHERE task_id = p_task_id AND status = 'active') INTO v_has_active;

    UPDATE tasks
       SET status = CASE WHEN v_has_active THEN 'in_progress' ELSE 'open' END,
           rejected_by = p_actor_id, rejected_at = now(), rejection_reason = btrim(p_reason),
           reported_by = NULL, reported_at = NULL,
           updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'JOB_REJECTED', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('rejected_by', p_actor_id, 'reason', btrim(p_reason)));

    FOR v_claimant IN
        SELECT member_id FROM task_commitments
         WHERE task_id = p_task_id AND status = 'active'
    LOOP
        INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                    dedup_key, payload, status)
        VALUES (p_chapter_id, 'JOB_REJECTED', v_claimant, 'tasks', p_task_id,
                'job_rejected:' || p_task_id || ':' || v_cycle || ':' || v_claimant,
                jsonb_build_object('task_id', p_task_id, 'rejected_by', p_actor_id,
                                   'reason', btrim(p_reason), 'title', v_task.title,
                                   'event_id', v_task.event_id),
                'pending')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_reject_task', p_idempotency_key, p_task_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 8. message_outbox event_type catalog extension (pattern: 0131) ────────────

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['JOB_REPORTED', 'JOB_APPROVED', 'JOB_REJECTED'];
    v_elem TEXT;
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_event_type_check';

    IF v_def IS NULL THEN
        v_vals := ARRAY['INVOICE_ISSUED', 'PAYMENT_APPROVED', 'PAYMENT_REJECTED',
                        'REFUND_ISSUED', 'ANNOUNCEMENT_PUBLISHED', 'ANNOUNCEMENT_SMS'];
    ELSE
        SELECT array_agg(DISTINCT m[1]) INTO v_vals
          FROM regexp_matches(v_def, '''([^'']+)''', 'g') AS m;
    END IF;

    FOREACH v_elem IN ARRAY v_new LOOP
        IF NOT (v_elem = ANY (v_vals)) THEN
            v_vals := array_append(v_vals, v_elem);
        END IF;
    END LOOP;

    SELECT string_agg(quote_literal(v), ', ') INTO v_list FROM unnest(v_vals) AS v;

    EXECUTE 'ALTER TABLE message_outbox DROP CONSTRAINT IF EXISTS message_outbox_event_type_check';
    EXECUTE format(
        'ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_event_type_check CHECK (event_type IN (%s))',
        v_list
    );
END $$;

-- ── 9. audit_logs action catalog extension (dual-format, pattern: 0100) ───────

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['JOB_REPORTED', 'JOB_APPROVED', 'JOB_REJECTED'];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        v_match := regexp_match(v_def, 'ARRAY\[(.+?)\]');
        IF v_match IS NOT NULL THEN
            FOREACH v_elem IN ARRAY string_to_array(v_match[1], ',') LOOP
                v_elem := trim(both '''' from regexp_replace(trim(v_elem), '::text$', ''));
                v_actions := v_actions || v_elem;
            END LOOP;
        ELSE
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
