-- Tasks service: chapter-level task groups and tasks.
--
-- Distinct from the operations engine's event_tasks (0003), which are
-- event-prep checklist items. A task_group may link to an event (and events
-- gain a linked_task_group_id in 0090) so the two surfaces can be unified
-- later. TODO(tasks): fold event_tasks into this model once the operations
-- engine consumes the tasks service.

CREATE TABLE IF NOT EXISTS task_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_task_groups_chapter_id ON task_groups(chapter_id);
CREATE INDEX IF NOT EXISTS ix_task_groups_event_id ON task_groups(event_id);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    group_id UUID REFERENCES task_groups(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    assigned_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'open',
    required BOOLEAN NOT NULL DEFAULT FALSE,
    due_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tasks_status_check CHECK (status IN ('open', 'in_progress', 'done', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_tasks_chapter_id ON tasks(chapter_id);
CREATE INDEX IF NOT EXISTS ix_tasks_group_id ON tasks(group_id);
CREATE INDEX IF NOT EXISTS ix_tasks_assigned_member_id ON tasks(assigned_member_id);
CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS ix_tasks_due_at ON tasks(due_at);

ALTER TABLE task_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS task_groups_select_chapter ON task_groups;
CREATE POLICY task_groups_select_chapter ON task_groups
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS tasks_select_chapter ON tasks;
CREATE POLICY tasks_select_chapter ON tasks
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── RPCs (service-role path: tenant guards + idempotency + audit) ─────────────

CREATE OR REPLACE FUNCTION tk_create_task(
    p_chapter_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_assigned_member_id UUID,
    p_group_id UUID,
    p_required BOOLEAN,
    p_due_at TIMESTAMPTZ,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
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

    INSERT INTO tasks (chapter_id, group_id, title, description, assigned_member_id,
                       created_by, required, due_at)
    VALUES (p_chapter_id, p_group_id, p_title, p_description, p_assigned_member_id,
            p_actor_id, COALESCE(p_required, FALSE), p_due_at)
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_TASK', p_actor_id, 'tasks', v_task.id,
            jsonb_build_object('title', p_title, 'assigned_member_id', p_assigned_member_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_create_task', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

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
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_update_task_status' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = p_task_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    UPDATE tasks SET status = p_status, updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

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
