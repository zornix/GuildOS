-- an_send_announcement_sms: the single atomic trust-boundary mutation for an
-- SMS blast. Inserts the append-only send-log row, fans out one message_outbox
-- row per recipient (dedup: announcement+member, so a re-send can never text
-- the same member twice for the same announcement), and writes audit_logs.
--
-- Recipient resolution + the confirmation-count check happen in the service
-- layer (api/announcements/services/sms.py); this RPC trusts the resolved
-- member-id list but re-verifies tenant boundaries (announcement and every
-- recipient must belong to p_chapter_id).
--
-- The audit row reuses the existing 'SEND_ANNOUNCEMENT' action with
-- metadata.channel='sms' rather than extending the shared audit_logs action
-- CHECK, to avoid cross-domain constraint churn while other domains migrate.

CREATE OR REPLACE FUNCTION an_send_announcement_sms(
    p_chapter_id UUID,
    p_announcement_id UUID,
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
    v_ann announcements%ROWTYPE;
    v_send announcement_sms_sends%ROWTYPE;
    v_count INTEGER;
    v_member UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id
           AND operation = 'an_send_announcement_sms'
           AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_recipient_member_ids IS NULL
       OR jsonb_typeof(p_recipient_member_ids) <> 'array' THEN
        RAISE EXCEPTION 'recipient_member_ids must be a jsonb array';
    END IF;
    v_count := jsonb_array_length(p_recipient_member_ids);

    SELECT * INTO v_ann FROM announcements
     WHERE id = p_announcement_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'announcement % not found in chapter %',
            p_announcement_id, p_chapter_id;
    END IF;

    -- SPEC §6 flow: the in-app feed post comes first; SMS amplifies it.
    IF v_ann.status <> 'sent' THEN
        RAISE EXCEPTION 'announcement % is not sent in-app (status %); post it to the feed before SMS',
            p_announcement_id, v_ann.status;
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

    INSERT INTO announcement_sms_sends
        (chapter_id, announcement_id, sender_id, recipient_count,
         recipient_member_ids, body_snapshot, delivery_mode, status)
    VALUES
        (p_chapter_id, p_announcement_id, p_actor_id, v_count,
         p_recipient_member_ids, p_body_snapshot, p_delivery_mode, 'queued')
    RETURNING * INTO v_send;

    -- One outbox row per recipient. dedup_key = announcement+member: a second
    -- blast for the same announcement never double-texts a member.
    FOR v_member IN
        SELECT value::uuid FROM jsonb_array_elements_text(p_recipient_member_ids)
    LOOP
        INSERT INTO message_outbox
            (chapter_id, event_type, member_id, target_table, target_id,
             dedup_key, payload, status, delivery_mode)
        VALUES
            (p_chapter_id, 'ANNOUNCEMENT_SMS', v_member,
             'announcement_sms_sends', v_send.id,
             'ANNOUNCEMENT_SMS:' || p_announcement_id || ':' || v_member,
             jsonb_build_object(
                 'announcement_id', p_announcement_id,
                 'send_id', v_send.id,
                 'title', v_ann.title,
                 'body', p_body_snapshot
             ),
             'pending', 'sms')
        ON CONFLICT (dedup_key) DO NOTHING;
    END LOOP;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SEND_ANNOUNCEMENT', p_actor_id,
            'announcement_sms_sends', v_send.id,
            jsonb_build_object(
                'channel', 'sms',
                'announcement_id', p_announcement_id,
                'recipient_count', v_count,
                'delivery_mode', p_delivery_mode
            ));

    v_result := to_jsonb(v_send);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'an_send_announcement_sms', p_idempotency_key,
                v_send.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
