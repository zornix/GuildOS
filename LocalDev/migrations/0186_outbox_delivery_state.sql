ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS provider_attempted_at TIMESTAMPTZ;
ALTER TABLE message_outbox ADD COLUMN IF NOT EXISTS provider_message_id TEXT;

CREATE OR REPLACE FUNCTION outbox_claim_batch(p_limit INT, p_chapter_id UUID DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows JSONB;
BEGIN
    -- Abandoned claim, provider never called: safe to retry; refund the unused attempt.
    UPDATE message_outbox
       SET status = 'pending',
           claimed_at = NULL,
           attempts = GREATEST(attempts - 1, 0)
     WHERE status = 'sending'
       AND claimed_at < now() - interval '15 minutes'
       AND provider_attempted_at IS NULL
       AND (p_chapter_id IS NULL OR chapter_id = p_chapter_id);

    -- The provider may have accepted the message. Never resend automatically.
    UPDATE message_outbox
       SET status = 'failed',
           last_error = 'delivery outcome unknown: the provider was called but the result was not recorded. Check with the recipient before retrying.'
     WHERE status = 'sending'
       AND claimed_at < now() - interval '15 minutes'
       AND provider_attempted_at IS NOT NULL
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

