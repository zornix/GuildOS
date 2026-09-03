-- Outbox claim step — issue #32 ("overlapping cron runs double-send SMS").
--
-- The drain used to SELECT status='pending' and start delivering, leaving every
-- row visible to every other reader for the whole duration of its Twilio call.
-- Vercel Cron fires every 5 minutes; a batch of 100 slow sends outlives that, so
-- the next run re-selected the same rows and sent every member a second message.
--
-- The fix is one claiming function: rows leave 'pending' for 'sending' in the
-- same statement that selects them, under FOR UPDATE SKIP LOCKED, so a second
-- worker sees neither the locked rows nor the claimed ones. Two things ride
-- along, because a claim without them strands rows:
--   * a reaper — a worker that dies mid-batch leaves 'sending' rows nobody owns;
--   * an attempt cap — a row that reliably kills the worker would otherwise be
--     reaped and re-claimed forever.
--
-- ponytail: the ceilings are constants in the function body — 15 minutes before
-- a claim is considered abandoned, 5 delivery attempts before a row is failed
-- for good. Move them to a settings table if an operator ever needs to tune them
-- per chapter.
--
-- Returns JSONB, not SETOF message_outbox as the issue sketched: the RPC shim
-- (api/platform/postgres.py::_RpcBuilder) calls `SELECT fn(...) AS result` and
-- fetches one row, so a set-returning function would surface a single unparsed
-- composite. Every other RPC in this schema returns JSONB for the same reason.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + the dynamic constraint rebuild pattern
-- from 0131 §, reused by 0142 §8, 0143 §3, 0145 §3 and 0150 §2.

-- ── 1. Claim bookkeeping columns ─────────────────────────────────────────────

ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN message_outbox.claimed_at IS
    'When a drain worker claimed this row (status=''sending''). Older than 15 minutes = abandoned, requeued by outbox_claim_batch.';

-- ── 2. status catalog: add 'sending' (pattern: 0150 §2) ──────────────────────
--
-- 'sending' = claimed by a drain worker, delivery in flight. Not terminal: the
-- worker closes it out to sent/simulated/failed, or the reaper requeues it.

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_new  TEXT[] := ARRAY['sending'];
    v_elem TEXT;
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'message_outbox'::regclass
       AND conname = 'message_outbox_status_check';

    IF v_def IS NULL THEN
        -- Baseline from 0070 + 0150.
        v_vals := ARRAY['pending', 'sent', 'failed', 'simulated'];
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

-- ── 3. The claim ─────────────────────────────────────────────────────────────
--
-- p_chapter_id narrows every step to one tenant (an operator draining a single
-- chapter must not requeue or fail another chapter's rows); the scheduled sweep
-- passes NULL and covers all of them.

CREATE OR REPLACE FUNCTION outbox_claim_batch(p_limit INT, p_chapter_id UUID DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows JSONB;
BEGIN
    -- Requeue abandoned claims: a worker that died mid-batch (or a Vercel
    -- function that hit its wall clock) left these owned by nobody.
    UPDATE message_outbox
       SET status = 'pending',
           claimed_at = NULL
     WHERE status = 'sending'
       AND claimed_at < now() - interval '15 minutes'
       AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id);

    -- Attempt cap: with a reaper in place, a row that reliably crashes the
    -- worker would be retried forever. Five deliveries attempted is enough.
    UPDATE message_outbox
       SET status = 'failed',
           last_error = 'attempt cap reached (5 delivery attempts)'
     WHERE status = 'pending'
       AND attempts >= 5
       AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id);

    WITH claimed AS (
        UPDATE message_outbox o
           SET status = 'sending',
               claimed_at = now(),
               attempts = o.attempts + 1
         WHERE o.id IN (
             SELECT id
               FROM message_outbox
              WHERE status = 'pending'
                AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id)
              ORDER BY created_at
              LIMIT p_limit
                FOR UPDATE SKIP LOCKED
         )
        RETURNING o.*
    )
    SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.created_at), '[]'::jsonb)
      INTO v_rows
      FROM claimed c;

    RETURN v_rows;
END $$;

COMMENT ON FUNCTION outbox_claim_batch(INT, UUID) IS
    'Claim up to p_limit pending outbox rows for one drain worker (issue #32). Requeues claims older than 15 minutes, fails rows past 5 attempts.';

-- ── 4. Nobody but the service role calls this ────────────────────────────────
-- It is a system worker's function: it mutates delivery state across every
-- chapter. The anon/authenticated guards are conditional because CI runs on a
-- bare Postgres where those Supabase roles do not exist.

REVOKE ALL ON FUNCTION outbox_claim_batch(INT, UUID) FROM PUBLIC;

DO $$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format(
                'REVOKE ALL ON FUNCTION outbox_claim_batch(INT, UUID) FROM %I', v_role
            );
        END IF;
    END LOOP;
END $$;
