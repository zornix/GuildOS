-- Self check-in writes attendance and its audit together; duplicate calls fail.
CREATE OR REPLACE FUNCTION at_checkin_self(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_attendance_id UUID;
    v_now TIMESTAMPTZ := now();
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('ev_attendance:' || p_event_id::text));
    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % not found in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_member_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % not found in chapter %', p_member_id, p_chapter_id;
    END IF;

    -- The conflict row is locked by the upsert, so simultaneous calls cannot
    -- both check in or write a second audit row.
    INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
    VALUES (p_chapter_id, p_event_id, p_member_id, TRUE, v_now, 'link')
    ON CONFLICT (event_id, member_id) DO UPDATE
        SET checked_in = TRUE, checked_in_at = v_now, method = 'link', chapter_id = p_chapter_id
        WHERE NOT attendance.checked_in
    RETURNING id INTO v_attendance_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'already checked in';
    END IF;

    PERFORM at_void_open_fines(p_chapter_id, p_event_id, p_member_id, p_member_id, 'self check-in');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'ATTENDANCE_OVERRIDDEN', p_member_id, 'attendance', v_attendance_id,
            jsonb_build_object('status', 'present', 'method', 'link', 'self_checkin', true,
                               'event_id', p_event_id, 'member_id', p_member_id));
    RETURN jsonb_build_object('attendance_id', v_attendance_id, 'checked_in_at', v_now);
END;
$$;
