-- Outbox drain support — GTMLarpChecklist 2.1 ("message_outbox has no drain")
-- and 2.2 ("success is reported for sends that never happened").
--
-- 2.1: the scheduled worker (api/cron/services/outbox_drain.py, invoked by Vercel
--      Cron via GET /api/cron/drain-outbox) needs per-row delivery bookkeeping —
--      how many times we tried, and why the last attempt failed.
-- 2.2: dry-run delivery must stop claiming 'sent'. A message that never touched
--      the network is now recorded as 'simulated', so the exec SMS log and the
--      outbox both tell the truth about what left the process.
--
-- Also extends the event catalog with PAYMENT_REMINDER, the outbox row written by
-- POST /api/memberadmin/remind/{member_id} (checklist 2.2's "Reminder queued"
-- endpoint, which previously queued nothing).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + the dynamic constraint rebuild pattern
-- established in 0131 §, reused verbatim by 0142 §8, 0143 §3 and 0145 §3.

-- ── 1. Delivery bookkeeping columns ──────────────────────────────────────────

ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS last_error TEXT;

COMMENT ON COLUMN message_outbox.attempts IS
    'Delivery attempts made by the drain worker. Incremented on every pass.';
COMMENT ON COLUMN message_outbox.last_error IS
    'Why the last attempt did not deliver (provider error, missing phone, unknown event_type).';

-- ── 2. status catalog: add 'simulated' (pattern: 0131) ───────────────────────
--
-- 'simulated' = MESSAGE_DELIVERY_MODE was dry_run; the message was rendered and
-- the row closed out, but no provider was contacted. Distinct from 'sent'.

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['simulated'];
    v_elem TEXT;
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_status_check';

    IF v_def IS NULL THEN
        -- Baseline from 0070.
        v_vals := ARRAY['pending', 'sent', 'failed'];
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

    EXECUTE 'ALTER TABLE message_outbox DROP CONSTRAINT IF EXISTS message_outbox_status_check';
    EXECUTE format(
        'ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_status_check CHECK (status IN (%s))',
        v_list
    );
END $$;

-- ── 3. event_type catalog extension (pattern: 0145 §3) ───────────────────────

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['PAYMENT_REMINDER'];
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
                        'JOB_REPORTED', 'JOB_APPROVED', 'JOB_REJECTED', 'EVENT_NOTIFY',
                        'SECURITY_ASSIGNED', 'SECURITY_SWAP_REQUESTED',
                        'SECURITY_SWAP_ACCEPTED', 'SECURITY_SWAP_DECLINED'];
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

-- ── 4. The drain worker's access path ────────────────────────────────────────
-- "oldest pending first, limit N" — a partial index keeps the sweep cheap as the
-- outbox accumulates terminal rows (rows are never deleted).

CREATE INDEX IF NOT EXISTS ix_message_outbox_pending_created_at
    ON message_outbox(created_at)
    WHERE status = 'pending';
