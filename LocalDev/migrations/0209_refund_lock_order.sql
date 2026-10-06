-- RV-03-4: refund and verify locked a member's invoices in different orders,
-- leaving a deadlock window. Before reversing, take the member's invoice locks
-- in the same canonical order 0166's verify/allocation path uses
-- (created_at ASC, id ASC); the reversal loop then processes rows in its own
-- business order (cancelled first, newest first) against already-held locks.
-- Body: 0207's tr_issue_refund with the pre-lock pass added.

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
    v_net_allocated BIGINT;
    v_to_reverse BIGINT;
    v_take BIGINT;
    v_row payment_allocations%ROWTYPE;
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

    -- Deadlock guard: take the member's invoice locks in 0166's canonical order
    -- before any reversal work touches them in business order.
    PERFORM 1 FROM unpaid_invoices
     WHERE chapter_id = p_chapter_id AND member_id = v_vp.member_id
     ORDER BY created_at ASC, id ASC
     FOR UPDATE;

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

    -- D3: the refund reopens what the payment covered. Unallocated credit is
    -- consumed first: after this refund the payment keeps
    -- amount − (earlier refunds + this one) cents, and its net allocations may
    -- not exceed that. Reverse cancelled coverage first, then newest allocations.
    SELECT COALESCE(SUM(CASE WHEN reverses_allocation_id IS NULL THEN amount_cents
                             ELSE -amount_cents END), 0)
      INTO v_net_allocated
      FROM payment_allocations
     WHERE verified_payment_id = p_verified_payment_id;
    v_to_reverse := GREATEST(0,
        v_net_allocated - (v_vp.amount_cents - v_already_refunded - p_amount_cents));

    FOR v_row IN
        SELECT pa.* FROM payment_allocations pa
          JOIN unpaid_invoices ui ON ui.id = pa.invoice_id
         WHERE pa.verified_payment_id = p_verified_payment_id
           AND pa.reverses_allocation_id IS NULL
           AND NOT EXISTS (
                SELECT 1 FROM payment_allocations r
                 WHERE r.reverses_allocation_id = pa.id)
         ORDER BY (ui.status = 'cancelled') DESC, pa.created_at DESC, pa.id DESC
    LOOP
        EXIT WHEN v_to_reverse <= 0;
        v_take := LEAST(v_to_reverse, v_row.amount_cents);

        -- Same convention as tr_reallocate_payment: a reversal row reverses the
        -- whole original; the part that stays covered is appended again.
        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents,
             reverses_allocation_id, allocated_by, note)
        VALUES
            (p_chapter_id, p_verified_payment_id, v_row.invoice_id, v_row.amount_cents,
             v_row.id, p_actor_id, p_reason);
        IF v_row.amount_cents > v_take THEN
            INSERT INTO payment_allocations
                (chapter_id, verified_payment_id, invoice_id, amount_cents, allocated_by, note)
            VALUES
                (p_chapter_id, p_verified_payment_id, v_row.invoice_id,
                 v_row.amount_cents - v_take, p_actor_id, p_reason);
        END IF;

        v_to_reverse := v_to_reverse - v_take;
        PERFORM tr_refresh_invoice_status(v_row.invoice_id);
    END LOOP;

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
