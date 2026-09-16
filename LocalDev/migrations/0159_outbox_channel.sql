-- Email for everything automatic, SMS for the two manual blasts (ADR-0005).
--
-- `message_outbox` used to be an SMS queue. It becomes a two-channel queue: the
-- drain (api/cron/services/outbox_drain.py) routes each row by `channel` — 'sms'
-- through Twilio with consent enforcement, 'email' through api/platform/email.py
-- with none (a member of a chapter gets their chapter's transactional mail).
--
-- 'email' is the default because everything except ANNOUNCEMENT_SMS and
-- EVENT_NOTIFY is automatic. Those two are produced inside plpgsql
-- (0132 an_send_announcement_sms, 0143/0145 ev_notify_event), so rather than
-- re-declare those functions to add one column, a BEFORE INSERT trigger pins
-- their channel. That also means a future plpgsql producer of either type
-- cannot get it wrong.
--
-- Idempotent: IF NOT EXISTS / DROP-then-ADD throughout.

-- ── 1. The channel column ────────────────────────────────────────────────────

ALTER TABLE message_outbox
    ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'email';

ALTER TABLE message_outbox DROP CONSTRAINT IF EXISTS message_outbox_channel_check;
ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_channel_check
    CHECK (channel IN ('email', 'sms'));

-- Backfill: every row already in the table predates the column, so it was
-- queued as an SMS only if it is one of the two manual blasts.
UPDATE message_outbox
   SET channel = 'sms'
 WHERE event_type IN ('ANNOUNCEMENT_SMS', 'EVENT_NOTIFY')
   AND channel <> 'sms';

-- ── 2. The two SMS event types are pinned to the SMS channel ─────────────────

CREATE OR REPLACE FUNCTION outbox_pin_sms_channel() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.event_type IN ('ANNOUNCEMENT_SMS', 'EVENT_NOTIFY') THEN
        NEW.channel := 'sms';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 0153's rule: nothing in public is executable by PUBLIC.
REVOKE ALL ON FUNCTION outbox_pin_sms_channel() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_outbox_pin_sms_channel ON message_outbox;
CREATE TRIGGER trg_outbox_pin_sms_channel
    BEFORE INSERT ON message_outbox
    FOR EACH ROW EXECUTE FUNCTION outbox_pin_sms_channel();

-- ── 3. The new email-only event types ────────────────────────────────────────
-- Same widen-in-place dance as 0131 / 0142 / 0145 / 0150: read the current
-- catalog out of the constraint definition, append, re-create.

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['SETUP_CODE', 'RESET_CODE', 'EVENT_CREATED',
                           'EVENT_ROLE_ASSIGNED'];
    v_elem TEXT;
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_event_type_check';

    IF v_def IS NULL THEN
        v_vals := ARRAY['INVOICE_ISSUED', 'PAYMENT_APPROVED', 'PAYMENT_REJECTED',
                        'REFUND_ISSUED', 'PAYMENT_REMINDER', 'ANNOUNCEMENT_PUBLISHED',
                        'ANNOUNCEMENT_SMS', 'JOB_REPORTED', 'JOB_APPROVED',
                        'JOB_REJECTED', 'EVENT_NOTIFY', 'SECURITY_ASSIGNED',
                        'SECURITY_SWAP_REQUESTED', 'SECURITY_SWAP_ACCEPTED',
                        'SECURITY_SWAP_DECLINED'];
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
