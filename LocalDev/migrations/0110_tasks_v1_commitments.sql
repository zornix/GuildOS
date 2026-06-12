-- Tasks V1 (GreekOS spec §4): event attachment, volunteering commitments, and
-- the append-only uncommit log (social accountability over hard locks).
--
-- Resolved decision #1: uncommit is ALWAYS allowed, but an uncommit is "late"
-- when it happens less than 24 hours before the linked event's start (events
-- already past count as late). Standalone tasks are never late.

-- ── 1. tasks: optional event attachment + 'committed' status ─────────────────

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS event_id UUID REFERENCES events(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_tasks_event_id ON tasks(event_id);

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('open', 'committed', 'in_progress', 'done', 'cancelled'));

-- ── 2. task_commitments (volunteering; multiple members per task) ────────────

CREATE TABLE IF NOT EXISTS task_commitments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'uncommitted', 'completed')),
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    uncommitted_at TIMESTAMPTZ
);

-- At most one ACTIVE commitment per (task, member); history rows may repeat.
CREATE UNIQUE INDEX IF NOT EXISTS uq_task_commitments_active
    ON task_commitments(task_id, member_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_task_commitments_chapter_id ON task_commitments(chapter_id);
CREATE INDEX IF NOT EXISTS ix_task_commitments_task_id ON task_commitments(task_id);
CREATE INDEX IF NOT EXISTS ix_task_commitments_member_id ON task_commitments(member_id);

ALTER TABLE task_commitments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS task_commitments_select_chapter ON task_commitments;
CREATE POLICY task_commitments_select_chapter ON task_commitments
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 3. task_commitment_log (append-only social-accountability artifact) ──────

CREATE TABLE IF NOT EXISTS task_commitment_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('commit', 'uncommit')),
    late BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT,
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    hours_before_event NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_task_commitment_log_chapter_id ON task_commitment_log(chapter_id);
CREATE INDEX IF NOT EXISTS ix_task_commitment_log_task_id ON task_commitment_log(task_id);
CREATE INDEX IF NOT EXISTS ix_task_commitment_log_member_id ON task_commitment_log(member_id);
CREATE INDEX IF NOT EXISTS ix_task_commitment_log_created_at ON task_commitment_log(created_at);

-- Append-only: same discipline as receipts/big_ledger (0005/0030).
CREATE OR REPLACE FUNCTION tk_block_commitment_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'task_commitment_log is append-only';
END;
$$;

DROP TRIGGER IF EXISTS task_commitment_log_immutable ON task_commitment_log;
CREATE TRIGGER task_commitment_log_immutable
    BEFORE UPDATE OR DELETE ON task_commitment_log
    FOR EACH ROW EXECUTE FUNCTION tk_block_commitment_log_mutation();

ALTER TABLE task_commitment_log ENABLE ROW LEVEL SECURITY;

-- Visible to the whole chapter by design (social accountability, spec §4).
DROP POLICY IF EXISTS task_commitment_log_select_chapter ON task_commitment_log;
CREATE POLICY task_commitment_log_select_chapter ON task_commitment_log
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 4. audit_logs action catalog extension (additive, concurrent-safe) ───────
-- Other domains extend this constraint in their own migrations; rebuild it from
-- the live definition instead of hardcoding the full list.

DO $$
DECLARE
    v_def TEXT;
    v_actions TEXT[];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        SELECT COALESCE(array_agg(m[1]), ARRAY[]::TEXT[]) INTO v_actions
          FROM regexp_matches(v_def, '''([^'']+)''', 'g') AS m;
        v_actions := (
            SELECT array_agg(DISTINCT a ORDER BY a)
              FROM unnest(v_actions || ARRAY['COMMIT_TASK', 'UNCOMMIT_TASK']) AS a
        );
        ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_action_check;
        EXECUTE format(
            'ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (action = ANY (%L::text[]))',
            v_actions
        );
    END IF;
END $$;

-- ── 5. RPCs ──────────────────────────────────────────────────────────────────

-- tk_create_task gains optional p_event_id. DROP (not OR REPLACE) because the
-- arity changes and an overload would make named-arg calls ambiguous; existing
-- callers omit p_event_id and keep working via the DEFAULT.
DROP FUNCTION IF EXISTS tk_create_task(UUID, TEXT, TEXT, UUID, UUID, BOOLEAN, TIMESTAMPTZ, UUID, TEXT);

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
    p_event_id UUID DEFAULT NULL
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

    INSERT INTO tasks (chapter_id, group_id, event_id, title, description, assigned_member_id,
                       created_by, required, due_at)
    VALUES (p_chapter_id, p_group_id, p_event_id, p_title, p_description, p_assigned_member_id,
            p_actor_id, COALESCE(p_required, FALSE), p_due_at)
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_TASK', p_actor_id, 'tasks', v_task.id,
            jsonb_build_object('title', p_title, 'assigned_member_id', p_assigned_member_id,
                               'event_id', p_event_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_create_task', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- Member volunteers (or an officer with tasks:assign commits another member —
-- the route enforces that; the RPC takes the actor separately for audit).
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
    v_commitment task_commitments%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_commit_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    IF v_task.status IN ('done', 'cancelled') THEN
        RAISE EXCEPTION 'task % is %, it cannot be committed to', p_task_id, v_task.status;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF EXISTS (SELECT 1 FROM task_commitments
                WHERE task_id = p_task_id AND member_id = p_member_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % already has an active commitment on task %', p_member_id, p_task_id;
    END IF;

    INSERT INTO task_commitments (chapter_id, task_id, member_id, status)
    VALUES (p_chapter_id, p_task_id, p_member_id, 'active')
    RETURNING * INTO v_commitment;

    INSERT INTO task_commitment_log (chapter_id, task_id, member_id, action, late, event_id)
    VALUES (p_chapter_id, p_task_id, p_member_id, 'commit', FALSE, v_task.event_id);

    IF v_task.status = 'open' THEN
        UPDATE tasks SET status = 'committed', updated_at = now()
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

-- Uncommit is ALWAYS allowed (no hard lock). Late = less than 24h before the
-- linked event's start (date + time, NULL time = start of day; past events are
-- late too). Standalone tasks are never late.
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
    v_late BOOLEAN := FALSE;
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
        v_late := v_hours < 24;
    END IF;

    UPDATE task_commitments
       SET status = 'uncommitted', uncommitted_at = now()
     WHERE id = v_commitment.id
    RETURNING * INTO v_commitment;

    INSERT INTO task_commitment_log
        (chapter_id, task_id, member_id, action, late, reason, event_id, hours_before_event)
    VALUES
        (p_chapter_id, p_task_id, p_member_id, 'uncommit', v_late, p_reason,
         v_task.event_id, v_hours);

    IF v_task.status NOT IN ('done', 'cancelled')
       AND NOT EXISTS (SELECT 1 FROM task_commitments
                        WHERE task_id = p_task_id AND status = 'active') THEN
        UPDATE tasks SET status = 'open', updated_at = now()
         WHERE id = p_task_id
        RETURNING * INTO v_task;
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UNCOMMIT_TASK', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('member_id', p_member_id, 'commitment_id', v_commitment.id,
                               'late', v_late, 'hours_before_event', v_hours,
                               'reason', p_reason));

    v_result := jsonb_build_object(
        'commitment', to_jsonb(v_commitment),
        'task_status', v_task.status,
        'late', v_late,
        'hours_before_event', v_hours
    );

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_uncommit_task', p_idempotency_key, v_commitment.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- tk_update_task_status: same signature as 0085 (backward compatible). When a
-- task transitions to 'done', every still-active commitment is credited as
-- 'completed' (members who uncommitted keep their 'uncommitted' history row).
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
