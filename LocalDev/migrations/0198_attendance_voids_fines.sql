-- F-004: attendance and excuse approval void every open event fine.
CREATE OR REPLACE FUNCTION at_void_open_fines(
    p_chapter_id UUID, p_event_id UUID, p_member_id UUID, p_actor_id UUID, p_reason TEXT
) RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    r RECORD;
    v_n INT := 0;
BEGIN
    FOR r IN
        SELECT id FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id AND kind = 'fine'
           AND source_event_id = p_event_id AND member_id = p_member_id
           AND status IN ('unpaid', 'partially_paid')
    LOOP
        PERFORM tr_void_invoice(p_chapter_id, r.id, p_actor_id, p_reason, NULL);
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END;
$$;
REVOKE ALL ON FUNCTION at_void_open_fines(UUID, UUID, UUID, UUID, TEXT) FROM PUBLIC;

CREATE OR REPLACE FUNCTION at_set_attendance(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_status TEXT,
    p_reason TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_attendance_id UUID;
    v_result JSONB;
    v_now TIMESTAMPTZ := now();
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'at_set_attendance' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % not found in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_member_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % not found in chapter %', p_member_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_actor_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'actor % is not an active member of chapter %', p_actor_id, p_chapter_id;
    END IF;

    IF p_status = 'excused' THEN
        IF p_reason IS NULL OR btrim(p_reason) = '' THEN
            RAISE EXCEPTION 'excuse reason is required when marking as excused';
        END IF;

        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, FALSE, NULL, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = FALSE, checked_in_at = NULL, method = 'manual'
        RETURNING id INTO v_attendance_id;

        -- Replace any existing excuse with an approved one stamped by the actor.
        DELETE FROM excuses WHERE event_id = p_event_id AND member_id = p_member_id;
        INSERT INTO excuses (chapter_id, event_id, member_id, reason, status,
                             reviewed_by, reviewed_at, submitted_at)
        VALUES (p_chapter_id, p_event_id, p_member_id, btrim(p_reason), 'approved',
                p_actor_id, v_now, v_now);

        PERFORM at_void_open_fines(p_chapter_id, p_event_id, p_member_id, p_actor_id, 'marked ' || p_status);

        v_result := jsonb_build_object('status', 'excused', 'method', 'manual');

    ELSIF p_status = 'absent' THEN
        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, FALSE, NULL, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = FALSE, checked_in_at = NULL, method = 'manual'
        RETURNING id INTO v_attendance_id;

        DELETE FROM excuses WHERE event_id = p_event_id AND member_id = p_member_id;

        v_result := jsonb_build_object('status', 'absent', 'method', 'manual');

    ELSE
        -- present (any status that is not excused/absent, matching the handler's else)
        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, TRUE, v_now, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = TRUE, checked_in_at = v_now, method = 'manual'
        RETURNING id INTO v_attendance_id;

        PERFORM at_void_open_fines(p_chapter_id, p_event_id, p_member_id, p_actor_id, 'marked ' || p_status);

        v_result := jsonb_build_object('status', 'checked_in', 'method', 'manual');
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'ATTENDANCE_OVERRIDDEN', p_actor_id, 'attendance', v_attendance_id,
            jsonb_build_object('status', p_status, 'event_id', p_event_id, 'member_id', p_member_id));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'at_set_attendance', p_idempotency_key, v_attendance_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION at_review_excuse(
    p_chapter_id UUID,
    p_excuse_id UUID,
    p_status TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_excuse excuses%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'at_review_excuse' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_status NOT IN ('approved', 'denied') THEN
        RAISE EXCEPTION 'status must be approved or denied';
    END IF;

    SELECT e.* INTO v_excuse
      FROM excuses e
      JOIN events ev ON ev.id = e.event_id
     WHERE e.id = p_excuse_id AND ev.chapter_id = p_chapter_id
     FOR UPDATE OF e;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'excuse % not found in chapter %', p_excuse_id, p_chapter_id;
    END IF;

    UPDATE excuses
       SET status = p_status, reviewed_by = p_actor_id, reviewed_at = now()
     WHERE id = p_excuse_id
    RETURNING * INTO v_excuse;

    IF p_status = 'approved' THEN
        PERFORM at_void_open_fines(p_chapter_id, v_excuse.event_id, v_excuse.member_id, p_actor_id, 'excuse approved');
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'EXCUSE_REVIEWED', p_actor_id, 'excuses', v_excuse.id,
            jsonb_build_object('decision', p_status,
                               'event_id', v_excuse.event_id,
                               'member_id', v_excuse.member_id));

    v_result := to_jsonb(v_excuse);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'at_review_excuse', p_idempotency_key, v_excuse.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
