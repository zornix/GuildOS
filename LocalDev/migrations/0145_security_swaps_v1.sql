-- Events V1 Phase 4 — Security assignments + swap requests
-- (docs/imp-ev-ph4.md). Implements docs/events-v1-spec.md §2.5 (Security),
-- §2.7 (swap notifications), Screen 6/7. Decisions D12–D14.
--
-- D12: a security assignment IS a tasks row (kind='security', people_needed=1,
-- status='in_progress' = pre-assigned/claimed) plus a pre-created active
-- commitment (the source of truth for the holder; assigned_member_id stays
-- NULL). Report/approve/reject reuse the tk_* lifecycle unchanged; claiming and
-- unclaiming are blocked (guards below); the swap flow is the only roster change.
-- Security jobs are excluded from the notify-gate job count and the
-- job_count/open_job_count decorations.
--
-- D13: swaps are a security_swap_requests table + one atomic accept RPC
-- (direct commitment ops inside the RPC — no nested tk_* calls, which the D12
-- guards would reject). One pending swap per assignment via a unique partial
-- index. No T-36h lock (a swap needs another member to accept = the
-- accountability). Update-guard trigger in the event_notification_sends (0143)
-- style: only status resolution may change, deletes blocked.
--
-- D14: security lives in the events domain (ev_* RPCs); manage gate reuses the
-- supervisor-OR-calendar:event:update rule; swap request/accept/decline are
-- identity-gated inside the RPCs. No new permission key, no RBAC seed.
--
-- Append-only migration rule: redefines the latest tk_* / ev_notify_event
-- bodies (copying the LATEST version — tk_uncommit_task from 0144, the rest
-- from 0142/0143 — never an earlier one) with one guard each; earlier
-- migrations untouched.

-- ── 1. tasks.kind ────────────────────────────────────────────────────────────

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'standard'
    CHECK (kind IN ('standard', 'security'));

-- Security is events-only (spec §2.5); belt for the RPC guards below.
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_security_event_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_security_event_check
    CHECK (kind <> 'security' OR event_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS ix_tasks_event_security
    ON tasks(event_id) WHERE kind = 'security';

-- ── 2. security_swap_requests ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_swap_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id          UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id            UUID NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    task_id             UUID NOT NULL REFERENCES tasks(id)    ON DELETE CASCADE,
    requester_member_id UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    target_member_id    UUID NOT NULL REFERENCES members(id)  ON DELETE CASCADE,
    note                TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID REFERENCES members(id) ON DELETE SET NULL
);

-- One pending swap per assignment (spec Screen 7, "prevents shotgunning").
CREATE UNIQUE INDEX IF NOT EXISTS uq_security_swaps_pending
    ON security_swap_requests(task_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS ix_security_swaps_chapter_id
    ON security_swap_requests(chapter_id);
CREATE INDEX IF NOT EXISTS ix_security_swaps_event_id
    ON security_swap_requests(event_id);
CREATE INDEX IF NOT EXISTS ix_security_swaps_target_member_id
    ON security_swap_requests(target_member_id);
CREATE INDEX IF NOT EXISTS ix_security_swaps_requester_member_id
    ON security_swap_requests(requester_member_id);

-- ── Append-only-ish guards (event_notification_sends 0143 pattern) ───────────
-- Only status resolution (status/resolved_at/resolved_by) may change, and only
-- while the row is still pending. Hard deletes blocked (tr_block_delete, 0005).

CREATE OR REPLACE FUNCTION ev_enforce_swap_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'security_swap_requests row is resolved; it cannot change';
    END IF;
    IF NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.chapter_id IS NOT DISTINCT FROM OLD.chapter_id
       AND NEW.event_id IS NOT DISTINCT FROM OLD.event_id
       AND NEW.task_id IS NOT DISTINCT FROM OLD.task_id
       AND NEW.requester_member_id IS NOT DISTINCT FROM OLD.requester_member_id
       AND NEW.target_member_id IS NOT DISTINCT FROM OLD.target_member_id
       AND NEW.note IS NOT DISTINCT FROM OLD.note
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
    THEN
        RETURN NEW;  -- only status/resolved_at/resolved_by may change
    END IF;

    RAISE EXCEPTION 'security_swap_requests is append-only; only status resolution may change';
END;
$$;

DROP TRIGGER IF EXISTS security_swap_requests_update_guard ON security_swap_requests;
CREATE TRIGGER security_swap_requests_update_guard
    BEFORE UPDATE ON security_swap_requests
    FOR EACH ROW EXECUTE FUNCTION ev_enforce_swap_update();

DROP TRIGGER IF EXISTS security_swap_requests_no_delete ON security_swap_requests;
CREATE TRIGGER security_swap_requests_no_delete
    BEFORE DELETE ON security_swap_requests
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

-- ── RLS (tenant table) ───────────────────────────────────────────────────────

ALTER TABLE security_swap_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS security_swap_requests_select_chapter ON security_swap_requests;
CREATE POLICY security_swap_requests_select_chapter ON security_swap_requests
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 3. message_outbox event_type catalog extension (pattern: 0143 §3) ────────

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['SECURITY_ASSIGNED', 'SECURITY_SWAP_REQUESTED',
                           'SECURITY_SWAP_ACCEPTED', 'SECURITY_SWAP_DECLINED'];
    v_elem TEXT;
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_event_type_check';

    IF v_def IS NULL THEN
        v_vals := ARRAY['INVOICE_ISSUED', 'PAYMENT_APPROVED', 'PAYMENT_REJECTED',
                        'REFUND_ISSUED', 'ANNOUNCEMENT_PUBLISHED', 'ANNOUNCEMENT_SMS',
                        'JOB_REPORTED', 'JOB_APPROVED', 'JOB_REJECTED', 'EVENT_NOTIFY'];
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

-- ── 4. audit_logs action catalog extension (dual-format, pattern: 0143 §4) ───

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    -- SECURITY_SWAP_CANCELLED is audit-only (seeded now even though the optional
    -- ev_cancel_security_swap RPC is not built this phase — avoids a second
    -- catalog migration later, per plan §2.5).
    v_new TEXT[] := ARRAY['SECURITY_ASSIGNED', 'SECURITY_REMOVED',
                          'SECURITY_SWAP_REQUESTED', 'SECURITY_SWAP_ACCEPTED',
                          'SECURITY_SWAP_DECLINED', 'SECURITY_SWAP_CANCELLED'];
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

-- ── 5. ev_assign_security — pre-assign a member to security ───────────────────
-- Task (kind='security', in_progress, people_needed=1) + active commitment +
-- 'commit' log row (matching tk_commit_task). Neutral outbox payload (never the
-- delinquency score). assigned_member_id stays NULL: the active commitment is
-- the sole source of truth for the holder.

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

-- ── 6. ev_remove_security — supervisor removes an assignment ──────────────────
-- Cancels any pending swap, uncommits the holder (log 'uncommit',
-- reason='security_removed'), cancels the task. Approved work stays credited.
-- No outbox (V1 non-goal).

CREATE OR REPLACE FUNCTION ev_remove_security(
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
    v_holder UUID;
    v_cancelled_swap_id UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'ev_remove_security' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % not found in chapter %', p_task_id, p_chapter_id;
    END IF;
    IF v_task.kind <> 'security' THEN
        RAISE EXCEPTION 'task % is not a security assignment', p_task_id;
    END IF;
    IF v_task.status = 'approved' THEN
        RAISE EXCEPTION 'security_already_approved';
    END IF;

    -- Cancel any pending swap for this assignment.
    UPDATE security_swap_requests
       SET status = 'cancelled', resolved_at = now(), resolved_by = p_actor_id
     WHERE task_id = p_task_id AND status = 'pending'
    RETURNING id INTO v_cancelled_swap_id;

    -- Uncommit the active holder (there is at most one — people_needed=1).
    SELECT member_id INTO v_holder FROM task_commitments
     WHERE task_id = p_task_id AND status = 'active'
     FOR UPDATE;

    IF v_holder IS NOT NULL THEN
        UPDATE task_commitments
           SET status = 'uncommitted', uncommitted_at = now()
         WHERE task_id = p_task_id AND member_id = v_holder AND status = 'active';

        INSERT INTO task_commitment_log
            (chapter_id, task_id, member_id, action, late, reason, event_id)
        VALUES
            (p_chapter_id, p_task_id, v_holder, 'uncommit', FALSE, 'security_removed', v_task.event_id);
    END IF;

    UPDATE tasks SET status = 'cancelled', updated_at = now()
     WHERE id = p_task_id
    RETURNING * INTO v_task;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_REMOVED', p_actor_id, 'tasks', p_task_id,
            jsonb_build_object('member_id', v_holder, 'event_id', v_task.event_id,
                               'cancelled_swap_id', v_cancelled_swap_id));

    v_result := to_jsonb(v_task);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_remove_security', p_idempotency_key, p_task_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 7. ev_request_security_swap — holder asks a target to take over ──────────
-- The unique partial index is the race guard: a unique_violation is caught and
-- re-raised as swap_already_pending (don't rely on a pre-check SELECT alone).

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

-- ── 8. ev_accept_security_swap — the atomic swap ─────────────────────────────
-- Direct commitment ops (no nested tk_* calls; the D12 guards would reject
-- them). Lock the task row FOR UPDATE before the flip (same serialization
-- discipline as tk_commit_task). Task status stays in_progress.

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

-- ── 9. ev_decline_security_swap — target declines ────────────────────────────

CREATE OR REPLACE FUNCTION ev_decline_security_swap(
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
         WHERE chapter_id = p_chapter_id AND operation = 'ev_decline_security_swap' AND key = p_idempotency_key;
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

    UPDATE security_swap_requests
       SET status = 'declined', resolved_at = now(), resolved_by = p_actor_id
     WHERE id = p_swap_id
    RETURNING * INTO v_swap;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SECURITY_SWAP_DECLINED', p_actor_id,
            'security_swap_requests', v_swap.id,
            jsonb_build_object('task_id', v_swap.task_id, 'event_id', v_swap.event_id,
                               'requester_member_id', v_swap.requester_member_id));

    INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                dedup_key, payload, status)
    VALUES (p_chapter_id, 'SECURITY_SWAP_DECLINED', v_swap.requester_member_id,
            'security_swap_requests', v_swap.id,
            'security_swap_declined:' || v_swap.id || ':' || v_swap.requester_member_id,
            jsonb_build_object('swap_id', v_swap.id, 'task_id', v_swap.task_id,
                               'event_id', v_swap.event_id,
                               'target_member_id', v_swap.target_member_id),
            'pending')
    ON CONFLICT (dedup_key) DO NOTHING;

    v_result := to_jsonb(v_swap);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_decline_security_swap', p_idempotency_key, v_swap.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 10. tk_commit_task — copy of 0142 body + security_preassigned guard ───────
-- Security assignments are pre-assigned (D12); claiming is blocked.

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

-- ── 11. tk_uncommit_task — copy of 0144 body + security_no_unclaim guard ──────
-- Copied from 0144 (the version with the initiative-parent branch — NOT 0142's).
-- Security cards show Request Swap instead of Unclaim (spec Screen 5).

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

-- ── 12. tk_update_task_status — copy of 0142 body + security guard ────────────
-- Roster changes on security tasks go only through the ev_* security RPCs; a
-- generic status flip must not bypass swap/remove semantics.

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

-- ── 13. ev_notify_event — copy of 0143 body + kind<>'security' job filter ─────
-- Security jobs are not claimable and must not let a security-only event pass
-- the ≥3-jobs completeness gate (D12).

CREATE OR REPLACE FUNCTION ev_notify_event(
    p_chapter_id UUID,
    p_event_id UUID,
    p_actor_id UUID,
    p_recipient_member_ids JSONB,
    p_body_snapshot TEXT,
    p_delivery_mode TEXT,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_event events%ROWTYPE;
    v_send event_notification_sends%ROWTYPE;
    v_member UUID;
    v_count INTEGER;
    v_supervisors INTEGER;
    v_organizers INTEGER;
    v_jobs INTEGER;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id
           AND operation = 'ev_notify_event'
           AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_recipient_member_ids IS NULL
       OR jsonb_typeof(p_recipient_member_ids) <> 'array'
       OR jsonb_array_length(p_recipient_member_ids) = 0 THEN
        RAISE EXCEPTION 'no_recipients';
    END IF;
    v_count := jsonb_array_length(p_recipient_member_ids);

    SELECT * INTO v_event FROM events
     WHERE id = p_event_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event % is not in chapter %', p_event_id, p_chapter_id;
    END IF;

    -- Tenant guard: every recipient must be a member of this chapter.
    IF EXISTS (
        SELECT 1
          FROM jsonb_array_elements_text(p_recipient_member_ids) AS r(member_id)
          LEFT JOIN members m
            ON m.id = r.member_id::uuid AND m.chapter_id = p_chapter_id
         WHERE m.id IS NULL
    ) THEN
        RAISE EXCEPTION 'recipient list contains members outside chapter %', p_chapter_id;
    END IF;

    -- Completeness gate (spec §2.7): >=1 supervisor, >=1 organizer, >=3 jobs.
    -- Security jobs (kind='security') are excluded — they are not claimable (D12).
    SELECT count(*) INTO v_supervisors FROM event_supervisors WHERE event_id = p_event_id;
    SELECT count(*) INTO v_organizers FROM event_organizers WHERE event_id = p_event_id;
    SELECT count(*) INTO v_jobs FROM tasks
     WHERE event_id = p_event_id AND chapter_id = p_chapter_id AND status <> 'cancelled'
       AND kind <> 'security';

    IF v_supervisors < 1 OR v_organizers < 1 OR v_jobs < 3 THEN
        RAISE EXCEPTION 'event_incomplete';
    END IF;

    -- Cooldown: at most one notify blast per event per hour.
    IF EXISTS (
        SELECT 1 FROM event_notification_sends
         WHERE event_id = p_event_id AND created_at > now() - interval '1 hour'
    ) THEN
        RAISE EXCEPTION 'notify_cooldown';
    END IF;

    INSERT INTO event_notification_sends
        (chapter_id, event_id, sender_id, recipient_count,
         recipient_member_ids, body_snapshot, delivery_mode, status)
    VALUES
        (p_chapter_id, p_event_id, p_actor_id, v_count,
         p_recipient_member_ids, p_body_snapshot, p_delivery_mode, 'queued')
    RETURNING * INTO v_send;

    -- One outbox row per recipient. dedup_key includes the send id (not just
    -- event+member) so a later re-notify of the same event fans out fresh
    -- rows instead of being silently dropped by the earlier send's dedup key.
    FOR v_member IN
        SELECT value::uuid FROM jsonb_array_elements_text(p_recipient_member_ids)
    LOOP
        INSERT INTO message_outbox
            (chapter_id, event_type, member_id, target_table, target_id,
             dedup_key, payload, status, delivery_mode)
        VALUES
            (p_chapter_id, 'EVENT_NOTIFY', v_member,
             'event_notification_sends', v_send.id,
             'EVENT_NOTIFY:' || p_event_id || ':' || v_send.id || ':' || v_member,
             jsonb_build_object(
                 'event_id', p_event_id,
                 'send_id', v_send.id,
                 'title', v_event.title,
                 'body', p_body_snapshot
             ),
             'pending', 'sms')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'EVENT_NOTIFY', p_actor_id,
            'event_notification_sends', v_send.id,
            jsonb_build_object(
                'event_id', p_event_id,
                'recipient_count', v_count,
                'delivery_mode', p_delivery_mode
            ));

    v_result := to_jsonb(v_send);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'ev_notify_event', p_idempotency_key,
                v_send.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
