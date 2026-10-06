-- F-014 (server half) · An officer records a payment for a member in one step
-- (decision D1).
--
-- tr_record_payment = tr_submit_payment (invoice given) or
-- tr_submit_balance_payment (no invoice), then tr_verify_payment_v2 on the new
-- submission as the officer. One plpgsql function, so both steps commit or
-- neither does. The inner idempotency keys are derived from the caller's key,
-- so a replay returns the stored verify result and writes nothing.

CREATE OR REPLACE FUNCTION tr_record_payment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_amount_cents BIGINT,
    p_method TEXT,
    p_actor_id UUID,
    p_invoice_id UUID DEFAULT NULL,
    p_reference TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_submission JSONB;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF p_invoice_id IS NOT NULL THEN
        v_submission := tr_submit_payment(
            p_chapter_id, p_member_id, p_invoice_id, p_amount_cents, p_method,
            p_reference, p_actor_id, p_idempotency_key || ':submit');
    ELSE
        v_submission := tr_submit_balance_payment(
            p_chapter_id, p_member_id, p_amount_cents, p_method,
            p_reference, p_idempotency_key || ':submit');
    END IF;

    RETURN tr_verify_payment_v2(
        p_chapter_id, (v_submission->>'id')::UUID, p_actor_id, p_idempotency_key || ':verify');
END;
$$;

-- Same exposure rule as every other RPC (0153): backend connection only.
REVOKE ALL ON FUNCTION tr_record_payment(UUID, UUID, BIGINT, TEXT, UUID, UUID, TEXT, TEXT) FROM PUBLIC;

DO $$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format(
                'REVOKE ALL ON FUNCTION tr_record_payment(UUID, UUID, BIGINT, TEXT, UUID, UUID, TEXT, TEXT) FROM %I',
                v_role
            );
        END IF;
    END LOOP;
END
$$;
