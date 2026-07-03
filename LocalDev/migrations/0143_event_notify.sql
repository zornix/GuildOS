-- Events V1 Phase 2 — notify gate: completeness-gated "Notify members" SMS
-- blast. Spec §2.7 / §5. Reuses the announcements SMS dispatch path
-- (api/announcements/services/sms.py dispatch_send, generalized with a
-- send_table param) rather than a second Twilio integration.
--
-- event_notification_sends is append-only in the big_ledger (0005) sense,
-- same shape/guard pattern as announcement_sms_sends (0131): rows are never
-- deleted, and the only mutation allowed is advancing `status`.

-- ── 1. event_notification_sends ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS event_notification_sends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES members(id) ON DELETE SET NULL,
    recipient_count INTEGER NOT NULL,
    recipient_member_ids JSONB NOT NULL,
    body_snapshot TEXT NOT NULL,
    delivery_mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_notification_sends_status_check CHECK (
        status IN ('queued', 'sent', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS ix_event_notification_sends_chapter_id
    ON event_notification_sends(chapter_id);
CREATE INDEX IF NOT EXISTS ix_event_notification_sends_event_id
    ON event_notification_sends(event_id, created_at DESC);

-- ── Append-only triggers (0005 big_ledger pattern, mirrors 0131) ─────────────

CREATE OR REPLACE FUNCTION ev_enforce_notify_send_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.chapter_id IS NOT DISTINCT FROM OLD.chapter_id
       AND NEW.event_id IS NOT DISTINCT FROM OLD.event_id
       AND NEW.sender_id IS NOT DISTINCT FROM OLD.sender_id
       AND NEW.recipient_count IS NOT DISTINCT FROM OLD.recipient_count
       AND NEW.recipient_member_ids IS NOT DISTINCT FROM OLD.recipient_member_ids
       AND NEW.body_snapshot IS NOT DISTINCT FROM OLD.body_snapshot
       AND NEW.delivery_mode IS NOT DISTINCT FROM OLD.delivery_mode
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
    THEN
        RETURN NEW;  -- only `status` may advance
    END IF;

    RAISE EXCEPTION 'event_notification_sends is append-only; only status may change';
END;
$$;

DROP TRIGGER IF EXISTS event_notification_sends_update_guard ON event_notification_sends;
CREATE TRIGGER event_notification_sends_update_guard
    BEFORE UPDATE ON event_notification_sends
    FOR EACH ROW EXECUTE FUNCTION ev_enforce_notify_send_update();

-- tr_block_delete is defined in 0005 and raises 'hard deletes are forbidden'.
DROP TRIGGER IF EXISTS event_notification_sends_no_delete ON event_notification_sends;
CREATE TRIGGER event_notification_sends_no_delete
    BEFORE DELETE ON event_notification_sends
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

-- ── RLS (tenant table) ───────────────────────────────────────────────────────

ALTER TABLE event_notification_sends ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_notification_sends_select_chapter ON event_notification_sends;
CREATE POLICY event_notification_sends_select_chapter ON event_notification_sends
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── 2. ev_notify_event — completeness-gated notify blast ────────────────────
-- Recipient resolution + the confirmation-count check happen in the service
-- layer (api/events/services/notifications.py); this RPC trusts the resolved
-- member-id list but re-verifies tenant boundaries and re-checks the
-- completeness gate (>=1 supervisor, >=1 organizer, >=3 non-cancelled jobs)
-- and a 1/hour cooldown per event, both as defense in depth.

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
    SELECT count(*) INTO v_supervisors FROM event_supervisors WHERE event_id = p_event_id;
    SELECT count(*) INTO v_organizers FROM event_organizers WHERE event_id = p_event_id;
    SELECT count(*) INTO v_jobs FROM tasks
     WHERE event_id = p_event_id AND chapter_id = p_chapter_id AND status <> 'cancelled';

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

-- ── 3. message_outbox event_type catalog extension (pattern: 0142) ──────────

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['EVENT_NOTIFY'];
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
                        'JOB_REPORTED', 'JOB_APPROVED', 'JOB_REJECTED'];
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

-- ── 4. audit_logs action catalog extension (dual-format, pattern: 0142) ─────

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['EVENT_NOTIFY'];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        -- Format A: action = ANY (ARRAY['X'::text, 'Y'::text, ...])
        v_match := regexp_match(v_def, 'ARRAY\[(.+?)\]');
        IF v_match IS NOT NULL THEN
            FOREACH v_elem IN ARRAY string_to_array(v_match[1], ',') LOOP
                v_elem := trim(both '''' from regexp_replace(trim(v_elem), '::text$', ''));
                v_actions := v_actions || v_elem;
            END LOOP;
        ELSE
            -- Format B: action = ANY ('{X,Y,...}'::text[])
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
