-- Chunk E · Refund RPC: tr_issue_refund (one atomic plpgsql txn).
-- Records a refund against exactly one verified payment, capped at that payment's
-- amount in aggregate across active refunds. Appends a signed-NEGATIVE REFUND_ISSUED
-- ledger entry (money leaving the chapter, member-scoped), writes an ISSUE_REFUND
-- audit row, and is idempotent on p_idempotency_key. Corrected via invalidation,
-- never deleted (invariant 1).

CREATE OR REPLACE FUNCTION tr_issue_refund(
    p_chapter_id UUID,
    p_verified_payment_id UUID,
    p_amount_cents BIGINT,
    p_reason TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_vp verified_payments%ROWTYPE;
    v_already_refunded BIGINT;
    v_refund refunds%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'issue_refund' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- Lock the source verified payment, chapter-scoped.
    SELECT * INTO v_vp FROM verified_payments
     WHERE id = p_verified_payment_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'verified payment % not found in chapter %', p_verified_payment_id, p_chapter_id;
    END IF;

    -- Cap: active refunds against this payment may not exceed it in aggregate.
    SELECT COALESCE(SUM(amount_cents), 0) INTO v_already_refunded FROM refunds
     WHERE verified_payment_id = p_verified_payment_id AND status = 'active';
    IF v_already_refunded + p_amount_cents > v_vp.amount_cents THEN
        RAISE EXCEPTION 'refund of % exceeds verified payment % (amount %, already refunded %)',
            p_amount_cents, p_verified_payment_id, v_vp.amount_cents, v_already_refunded;
    END IF;

    INSERT INTO refunds
        (chapter_id, member_id, verified_payment_id, amount_cents, reason, officer_id, reviewed_by, reviewed_at, status)
    VALUES
        (p_chapter_id, v_vp.member_id, p_verified_payment_id, p_amount_cents, p_reason, p_actor_id, p_actor_id, now(), 'active')
    RETURNING * INTO v_refund;

    -- Money out, member-scoped, signed negative.
    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'REFUND_ISSUED', -p_amount_cents, v_vp.member_id, 'refunds', v_refund.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'ISSUE_REFUND', p_actor_id, 'refunds', v_refund.id,
            jsonb_build_object('verified_payment_id', p_verified_payment_id,
                               'amount_cents', p_amount_cents, 'reason', p_reason));

    v_result := to_jsonb(v_refund);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'issue_refund', p_idempotency_key, v_refund.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
