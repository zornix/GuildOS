-- Events V1 Phase 3 — Initiatives (docs/imp-ev-ph3.md). Implements
-- docs/events-v1-spec.md §2.2 (Initiative), §2.4 (jobs lifecycle shared with
-- initiatives), §2.6 (calendar), §5 (permissions). "An initiative is an event
-- with the officer layer deleted" (spec §2.2): no supervisors, no
-- attendance/fines, no notify gate. D8: initiatives are a separate table
-- (mirrors events + event_supervisors shape-for-shape), not a flavor of
-- events. D11: the job RPC surface (tasks.tk_*) is reused, not duplicated.

-- ── 1. initiatives ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS initiatives (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id  UUID NOT NULL REFERENCES chapters(id),
    title       TEXT NOT NULL,
    description TEXT,
    date        DATE NOT NULL,          -- Open Item 1: start is always required
    time        TIME NOT NULL,
    end_date    DATE,
    end_time    TIME,
    created_by  UUID NOT NULL REFERENCES members(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_initiatives_chapter_id_date ON initiatives(chapter_id, date);

ALTER TABLE initiatives ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS initiatives_select_chapter ON initiatives;
CREATE POLICY initiatives_select_chapter ON initiatives
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 2. initiative_chairs (mirrors event_supervisors, 0141) ───────────────

CREATE TABLE IF NOT EXISTS initiative_chairs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id    UUID NOT NULL REFERENCES chapters(id),
    initiative_id UUID NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE,
    member_id     UUID NOT NULL REFERENCES members(id),
    is_creator    BOOLEAN NOT NULL DEFAULT false,
    added_by      UUID REFERENCES members(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (initiative_id, member_id)
);

CREATE INDEX IF NOT EXISTS ix_initiative_chairs_chapter_id ON initiative_chairs(chapter_id);
CREATE INDEX IF NOT EXISTS ix_initiative_chairs_initiative_id ON initiative_chairs(initiative_id);
CREATE INDEX IF NOT EXISTS ix_initiative_chairs_member_id ON initiative_chairs(member_id);

ALTER TABLE initiative_chairs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS initiative_chairs_select_chapter ON initiative_chairs;
CREATE POLICY initiative_chairs_select_chapter ON initiative_chairs
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 3. tasks.initiative_id + single-parent exclusivity ───────────────────

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS
    initiative_id UUID REFERENCES initiatives(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_tasks_initiative_id ON tasks(initiative_id)
    WHERE initiative_id IS NOT NULL;

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_single_parent_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_single_parent_check
    CHECK (event_id IS NULL OR initiative_id IS NULL);

-- ── 4. in_create_initiative ───────────────────────────────────────────────
-- Validates every chair id belongs to the chapter (member_not_in_chapter);
-- the actor is auto-added as a chair (is_creator = true) if not already
-- present in p_chair_member_ids.

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

-- ── 5. in_update_initiative ───────────────────────────────────────────────
-- NULL params mean "unchanged" (COALESCE); date/time are NOT NULL columns so
-- they can never be cleared. Actor must be an assigned chair (defense in
-- depth; the service layer already checks this via is_assigned_chair).

CREATE OR REPLACE FUNCTION in_update_initiative(
    p_chapter_id UUID,
    p_initiative_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_date DATE,
    p_time TIME,
    p_end_date DATE,
    p_end_time TIME,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_initiative initiatives%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'in_update_initiative' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_initiative FROM initiatives
     WHERE id = p_initiative_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'initiative % not found in chapter %', p_initiative_id, p_chapter_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM initiative_chairs
         WHERE initiative_id = p_initiative_id AND member_id = p_actor_id
    ) THEN
        RAISE EXCEPTION 'not_assigned_chair';
    END IF;

    UPDATE initiatives
       SET title       = COALESCE(p_title, title),
           description = COALESCE(p_description, description),
           date        = COALESCE(p_date, date),
           time        = COALESCE(p_time, time),
           end_date    = COALESCE(p_end_date, end_date),
           end_time    = COALESCE(p_end_time, end_time),
           updated_at  = now()
     WHERE id = p_initiative_id
    RETURNING * INTO v_initiative;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'INITIATIVE_UPDATED', p_actor_id, 'initiatives', p_initiative_id,
            jsonb_build_object('title', v_initiative.title));

    v_result := to_jsonb(v_initiative);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'in_update_initiative', p_idempotency_key, p_initiative_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 6. in_add_chair — add a co-chair (idempotent) ────────────────────────

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

-- ── 7. in_remove_chair — remove a co-chair (min-1: last_chair) ───────────

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

-- ── 8. tk_create_task gains p_initiative_id ───────────────────────────────
-- DROP (not OR REPLACE) because the arity changes; existing callers omit
-- p_initiative_id and keep working via the DEFAULT (0110/0142 precedent).

DROP FUNCTION IF EXISTS tk_create_task(UUID, TEXT, TEXT, UUID, UUID, BOOLEAN, TIMESTAMPTZ, UUID, TEXT, UUID);

CREATE OR REPLACE FUNCTION tk_create_task(
    p_chapter_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_assigned_member_id UUID,
    p_group_id UUID,
    p_required BOOLEAN,
    p_due_at TIMESTAMPTZ,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL,
    p_event_id UUID DEFAULT NULL,
    p_initiative_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_task tasks%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_create_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_event_id IS NOT NULL AND p_initiative_id IS NOT NULL THEN
        RAISE EXCEPTION 'task_two_parents';
    END IF;

    IF p_assigned_member_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM members WHERE id = p_assigned_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_assigned_member_id, p_chapter_id;
    END IF;
    IF p_group_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM task_groups WHERE id = p_group_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'task group % is not in chapter %', p_group_id, p_chapter_id;
    END IF;
    IF p_event_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF p_initiative_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM initiatives WHERE id = p_initiative_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'initiative_not_found';
    END IF;

    INSERT INTO tasks (chapter_id, group_id, event_id, initiative_id, title, description,
                       assigned_member_id, created_by, required, due_at)
    VALUES (p_chapter_id, p_group_id, p_event_id, p_initiative_id, p_title, p_description,
            p_assigned_member_id, p_actor_id, COALESCE(p_required, FALSE), p_due_at)
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_TASK', p_actor_id, 'tasks', v_task.id,
            jsonb_build_object('title', p_title, 'assigned_member_id', p_assigned_member_id,
                               'event_id', p_event_id, 'initiative_id', p_initiative_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_create_task', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 9. tk_uncommit_task — PHASE3 SEAM resolved: initiative start ─────────
-- Same signature (CREATE OR REPLACE). Adds the initiative branch alongside
-- the event branch so the T-36h hard lock (D2) also anchors on initiative
-- start (spec §2.4: "36 hours before event/initiative start").

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

    IF v_task.event_id IS NOT NULL THEN
        SELECT (e.date + COALESCE(e.time, TIME '00:00'))::timestamptz
          INTO v_event_start
          FROM events e WHERE e.id = v_task.event_id;
        v_hours := ROUND((EXTRACT(EPOCH FROM (v_event_start - now())) / 3600.0)::numeric, 2);
    END IF;

    IF v_task.initiative_id IS NOT NULL THEN
        SELECT (i.date + COALESCE(i.time, TIME '00:00'))::timestamptz
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

-- ── 10. tk_report_done — fan JOB_REPORTED to initiative_chairs too ───────
-- Same signature (CREATE OR REPLACE). The event-supervisor loop is
-- unchanged; a new loop fans out to initiative_chairs when the job's parent
-- is an initiative. A task has at most one parent (tasks_single_parent_check),
-- so at most one of the two loops ever produces rows for a given task.

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

    -- One outbox row per initiative chair (PHASE3): the initiative twin of
    -- the supervisor loop above. Parentless/event jobs have no chairs here.
    FOR v_approver IN
        SELECT member_id FROM initiative_chairs WHERE initiative_id = v_task.initiative_id
    LOOP
        INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                    dedup_key, payload, status)
        VALUES (p_chapter_id, 'JOB_REPORTED', v_approver, 'tasks', p_task_id,
                'job_reported:' || p_task_id || ':' || v_cycle || ':' || v_approver,
                jsonb_build_object('task_id', p_task_id, 'reported_by', p_member_id,
                                   'title', v_task.title, 'initiative_id', v_task.initiative_id),
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

-- ── 11. audit_logs action catalog extension (dual-format, pattern: 0142) ─

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['INITIATIVE_CREATED', 'INITIATIVE_UPDATED',
                           'INITIATIVE_CHAIR_ADDED', 'INITIATIVE_CHAIR_REMOVED'];
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

-- ── 12. Permission seed (0130 pattern) ────────────────────────────────────
-- calendar:initiative:create / :update → the six chair roles + admin only
-- (spec §5: exec —, member —). No :delete key — no delete flow in V1.

INSERT INTO permissions (key, description) VALUES
    ('calendar:initiative:create', 'Create chapter initiatives (chair roles)'),
    ('calendar:initiative:update', 'Update chapter initiatives (chair roles)')
ON CONFLICT (key) DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT x.role, y.perm
FROM (VALUES ('admin'), ('risk_chair'), ('social_chair'), ('recruitment_chair'),
             ('brotherhood_chair'), ('philanthropy_chair'), ('standards_chair')) AS x(role)
CROSS JOIN (VALUES ('calendar:initiative:create'), ('calendar:initiative:update')) AS y(perm)
ON CONFLICT DO NOTHING;
