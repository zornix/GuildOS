-- Review fix of 0210: lock tasks rows BEFORE touching their commitments, the
-- order tk_commit_task (0175), tk_uncommit_task (0197) and the swap paths use.
-- 0210 updated task_commitments first, opening a deadlock with a concurrent
-- (un)commit and a race that could leave an active claim on a cancelled event.
-- Body: identical to 0210 except the tasks UPDATE moved above the swap/claim
-- statements.
CREATE OR REPLACE FUNCTION ev_delete_or_cancel_event(
    p_chapter_id UUID, p_event_id UUID, p_actor_id UUID
) RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_event events%ROWTYPE;
BEGIN
    SELECT * INTO v_event FROM events
     WHERE id = p_event_id AND chapter_id = p_chapter_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event % not found in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF v_event.cancelled THEN
        RETURN jsonb_build_object('deleted', false, 'cancelled', true);
    END IF;
    IF NOT (
        EXISTS (SELECT 1 FROM attendance WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM excuses WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM tasks WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM fines WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM event_notification_sends WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM security_swap_requests WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM attendance_sessions WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM task_commitment_log WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM event_roles WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM event_tasks WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM post_event_reports WHERE event_id = p_event_id)
        OR EXISTS (SELECT 1 FROM unpaid_invoices WHERE source_event_id = p_event_id)
    ) THEN
        DELETE FROM events WHERE id = p_event_id;
        RETURN jsonb_build_object('deleted', true, 'cancelled', false);
    END IF;
    UPDATE events SET cancelled = true, required = false WHERE id = p_event_id;
    UPDATE checkin_links SET active = false WHERE event_id = p_event_id AND active;
    -- Lock and cancel the tasks first (canonical task→commitment order).
    UPDATE tasks SET status = 'cancelled', updated_at = now()
     WHERE event_id = p_event_id AND status NOT IN ('done', 'approved', 'cancelled');
    -- Resolve pending swaps and release every active holder, as in 0145.
    UPDATE security_swap_requests
       SET status = 'cancelled', resolved_at = now(), resolved_by = p_actor_id
     WHERE chapter_id = p_chapter_id AND event_id = p_event_id AND status = 'pending';
    WITH released AS (
        UPDATE task_commitments tc
           SET status = 'uncommitted', uncommitted_at = now()
          FROM tasks t
         WHERE tc.task_id = t.id AND tc.chapter_id = p_chapter_id
           AND t.chapter_id = p_chapter_id AND t.event_id = p_event_id
           AND tc.status = 'active'
        RETURNING tc.task_id, tc.member_id
    )
    INSERT INTO task_commitment_log
        (chapter_id, task_id, member_id, action, late, reason, event_id)
    SELECT p_chapter_id, task_id, member_id, 'uncommit', FALSE, 'event_cancelled', p_event_id
      FROM released;
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UPDATE_EVENT', p_actor_id, 'events', p_event_id,
            jsonb_build_object('cancelled', true));
    RETURN jsonb_build_object('deleted', false, 'cancelled', true);
END;
$$;
