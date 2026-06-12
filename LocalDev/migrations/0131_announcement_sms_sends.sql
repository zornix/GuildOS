-- Announcement SMS send log (SPEC §6: every send logged with sender, visible
-- to exec) + outbox event-type extension for per-recipient SMS fan-out.
--
-- announcement_sms_sends is append-only in the big_ledger (0005) sense: rows
-- are never deleted, and the only mutation allowed is advancing `status`
-- (queued -> sent/failed by the dispatcher). Everything else is frozen at
-- send time — body_snapshot in particular is the exact text that went out.

CREATE TABLE IF NOT EXISTS announcement_sms_sends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    announcement_id UUID NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES members(id) ON DELETE SET NULL,
    recipient_count INTEGER NOT NULL,
    recipient_member_ids JSONB NOT NULL,
    body_snapshot TEXT NOT NULL,
    delivery_mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT announcement_sms_sends_status_check CHECK (
        status IN ('queued', 'sent', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS ix_announcement_sms_sends_chapter_id
    ON announcement_sms_sends(chapter_id);
CREATE INDEX IF NOT EXISTS ix_announcement_sms_sends_announcement_id
    ON announcement_sms_sends(announcement_id);
CREATE INDEX IF NOT EXISTS ix_announcement_sms_sends_created_at
    ON announcement_sms_sends(created_at);

-- ── Append-only triggers (0005 big_ledger pattern) ───────────────────────────

CREATE OR REPLACE FUNCTION an_enforce_sms_send_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.chapter_id IS NOT DISTINCT FROM OLD.chapter_id
       AND NEW.announcement_id IS NOT DISTINCT FROM OLD.announcement_id
       AND NEW.sender_id IS NOT DISTINCT FROM OLD.sender_id
       AND NEW.recipient_count IS NOT DISTINCT FROM OLD.recipient_count
       AND NEW.recipient_member_ids IS NOT DISTINCT FROM OLD.recipient_member_ids
       AND NEW.body_snapshot IS NOT DISTINCT FROM OLD.body_snapshot
       AND NEW.delivery_mode IS NOT DISTINCT FROM OLD.delivery_mode
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
    THEN
        RETURN NEW;  -- only `status` may advance
    END IF;

    RAISE EXCEPTION 'announcement_sms_sends is append-only; only status may change';
END;
$$;

DROP TRIGGER IF EXISTS announcement_sms_sends_update_guard ON announcement_sms_sends;
CREATE TRIGGER announcement_sms_sends_update_guard
    BEFORE UPDATE ON announcement_sms_sends
    FOR EACH ROW EXECUTE FUNCTION an_enforce_sms_send_update();

-- tr_block_delete is defined in 0005 and raises 'hard deletes are forbidden'.
DROP TRIGGER IF EXISTS announcement_sms_sends_no_delete ON announcement_sms_sends;
CREATE TRIGGER announcement_sms_sends_no_delete
    BEFORE DELETE ON announcement_sms_sends
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

-- ── RLS (tenant table; same shape as announcements in 0086) ──────────────────

ALTER TABLE announcement_sms_sends ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS announcement_sms_sends_select_chapter ON announcement_sms_sends;
CREATE POLICY announcement_sms_sends_select_chapter ON announcement_sms_sends
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- ── Outbox event catalog: add ANNOUNCEMENT_SMS ───────────────────────────────
-- Rebuilt from the LIVE constraint definition (not a hard-coded list) so a
-- concurrently-added event type from another domain's migration is preserved.

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_event_type_check';

    IF v_def IS NULL THEN
        -- Baseline from 0070 + 0086.
        v_vals := ARRAY['INVOICE_ISSUED', 'PAYMENT_APPROVED', 'PAYMENT_REJECTED',
                        'REFUND_ISSUED', 'ANNOUNCEMENT_PUBLISHED'];
    ELSE
        SELECT array_agg(DISTINCT m[1]) INTO v_vals
          FROM regexp_matches(v_def, '''([^'']+)''', 'g') AS m;
    END IF;

    IF NOT ('ANNOUNCEMENT_SMS' = ANY (v_vals)) THEN
        v_vals := array_append(v_vals, 'ANNOUNCEMENT_SMS');
    END IF;

    SELECT string_agg(quote_literal(v), ', ') INTO v_list FROM unnest(v_vals) AS v;

    EXECUTE 'ALTER TABLE message_outbox DROP CONSTRAINT IF EXISTS message_outbox_event_type_check';
    EXECUTE format(
        'ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_event_type_check CHECK (event_type IN (%s))',
        v_list
    );
END $$;
