-- Before-Frontend unblocks (docs/B4FEND-FIX.md) — the backend half of the seven
-- gaps that block Events V1 Phase 5. Four independent sections:
--
--   1. announcements calendar columns (D15: calendar presence, NOT delayed SMS)
--   2. audit_logs action catalog += UPDATE_TASK / CANCEL_TASK
--   3. tk_update_task / tk_cancel_task (D16: job delete is cancel, never a
--      hard DELETE; security jobs are refused — roster changes stay on ev_*)
--   4. ev_cancel_security_swap (requester withdraws a pending swap; the RPC
--      was cut as optional in Phase 4, its audit action was already seeded)
--
-- Append-only migration rule: no existing function body is copied-and-patched;
-- every function here is brand new. tk_update_task_status, tk_commit_task,
-- tk_create_task, every other ev_*/in_*/an_* stay exactly as their latest
-- migration left them.

-- ── 1. Announcements calendar columns (D15) ──────────────────────────────────
-- Nullable on purpose: every existing row is a draft or a sent feed post with no
-- calendar slot. Service-layer validation (not a DB CHECK) accepts calendar_time
-- only when calendar_date is set, so existing create_draft callers keep working.
-- A sent row without calendar_date is a feed post that never hits the calendar.
-- hidden_from_calendar is how DELETE /api/announcements/{id} retires a *sent*
-- row without touching the SMS log.

ALTER TABLE announcements
    ADD COLUMN IF NOT EXISTS calendar_date        DATE,
    ADD COLUMN IF NOT EXISTS calendar_time        TIME,
    ADD COLUMN IF NOT EXISTS hidden_from_calendar BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS ix_announcements_calendar
    ON announcements (chapter_id, calendar_date)
    WHERE status = 'sent' AND hidden_from_calendar = FALSE AND calendar_date IS NOT NULL;

-- ── 2. audit_logs action catalog extension (dual-format, pattern: 0145 §4) ───

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['UPDATE_TASK', 'CANCEL_TASK'];
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

-- ── 3. tk_update_task — edit a job's own fields (D16) ────────────────────────
-- NULL param = leave that column alone (PATCH semantics). Parent (event_id /
-- initiative_id), kind, status and assigned_member_id are immutable here; the
-- lifecycle RPCs own those. No message_outbox row: editing a job is not news.

CREATE OR REPLACE FUNCTION tk_update_task(
    p_chapter_id UUID,
    p_task_id UUID,
    p_title TEXT,
    p_description TEXT,
    p_people_needed INT,
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
    v_active_count INT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_update_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    -- Security assignments (D12) are managed through the ev_* security RPCs.
    IF v_task.kind = 'security' THEN
        RAISE EXCEPTION 'security_no_edit';
    END IF;

    -- Editing is a to-do / in-progress action; once reported it is the
    -- approver's call, and cancelled jobs are done being edited.
    IF v_task.status NOT IN ('open', 'in_progress') THEN
        RAISE EXCEPTION 'job_not_editable';
    END IF;

    IF p_title IS NOT NULL AND btrim(p_title) = '' THEN
        RAISE EXCEPTION 'job_title_required';
    END IF;

    IF p_people_needed IS NOT NULL THEN
        IF p_people_needed < 1 THEN
            RAISE EXCEPTION 'job_people_needed_invalid';
        END IF;
        SELECT count(*) INTO v_active_count FROM task_commitments
         WHERE task_id = p_task_id AND status = 'active';
        IF p_people_needed < v_active_count THEN
            RAISE EXCEPTION 'job_capacity_below_claims';
        END IF;
    END IF;

    UPDATE tasks
       SET title         = COALESCE(btrim(p_title), title),
           description   = COALESCE(p_description, description),
           people_needed = COALESCE(p_people_needed, people_needed),
           due_at        = COALESCE(p_due_at, due_at),
           updated_at    = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UPDATE_TASK', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('title', v_task.title,
                               'people_needed', v_task.people_needed,
                               'due_at', v_task.due_at));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_update_task', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── tk_cancel_task — job delete IS cancel (D16) ──────────────────────────────
-- open-only: an in-progress job has claimants, and the last unclaim already
-- reverts a job to open, so "no claimants" and "open" are the same rule stated
-- once. Commitments are untouched (there are none while open).

CREATE OR REPLACE FUNCTION tk_cancel_task(
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
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'tk_cancel_task' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;

    IF v_task.kind = 'security' THEN
        RAISE EXCEPTION 'security_no_cancel';
    END IF;

    IF v_task.status <> 'open' THEN
        RAISE EXCEPTION 'job_not_cancellable';
    END IF;

    UPDATE tasks SET status = 'cancelled', updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CANCEL_TASK', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('title', v_task.title, 'event_id', v_task.event_id,
                               'initiative_id', v_task.initiative_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'tk_cancel_task', p_idempotency_key, v_task.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 4. ev_cancel_security_swap — the REQUESTER withdraws ─────────────────────
-- Shape copied from ev_decline_security_swap (0145 §9): same pending /
-- swap_wrong_state / not-found / tenancy / idempotency / FOR UPDATE guards.
-- Differences: the actor must be the requester (not the target), the resolved
-- status is 'cancelled', and there is NO message_outbox row (Phase 4 decision:
-- withdrawing your own ask is not news for anyone). SECURITY_SWAP_CANCELLED was
-- already seeded into the audit catalog by 0145 §4 — not re-seeded here.
--
-- Unblocks the unique-partial-index slot on an assignment whose target simply
-- never answered; ev_remove_security stays the supervisor-side escape hatch.

CREATE OR REPLACE FUNCTION ev_cancel_security_swap(
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
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_cancel_security_swap' AND key = p_idempotency_key;
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
    IF p_actor_id <> v_swap.requester_member_id THEN
        RAISE EXCEPTION 'not_swap_requester';
    END IF;

    UPDATE security_swap_requests
       SET status = 'cancelled', resolved_at = now(), resolved_by = p_actor_id
     WHERE id = p_swap_id
    RETURNING * INTO v_swap;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_SWAP_CANCELLED', p_actor_id,
            'security_swap_requests', v_swap.id,
            jsonb_build_object('task_id', v_swap.task_id, 'event_id', v_swap.event_id,
                               'target_member_id', v_swap.target_member_id));

    v_result := to_jsonb(v_swap);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_cancel_security_swap', p_idempotency_key, v_swap.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
