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
    -- Serialize sends per event so the one-hour cooldown cannot be raced (F-013).
    PERFORM pg_advisory_xact_lock(hashtext('ev_notify:' || p_event_id::text));
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
