-- Chunk C · Payment RPCs: tr_verify_payment, tr_reject_payment.
-- Each is one plpgsql txn (atomic). The double-verify race is closed by FOR UPDATE
-- on the submission row PLUS the UNIQUE(submission_id) backstop on verified_payments:
-- under concurrency at most one verified_payment per submission can ever exist.

-- ── verify a payment submission ──────────────────────────────────────────────
-- Creates verified_payment + immutable receipt + PAYMENT_RECEIVED ledger entry,
-- approves the submission, and transitions the invoice. Idempotent: replaying an
-- already-approved submission returns the existing verified_payment with
-- "_created": false (so the service knows not to re-notify).
CREATE OR REPLACE FUNCTION tr_verify_payment(
    p_chapter_id UUID,
    p_submission_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_submission payment_submissions%ROWTYPE;
    v_invoice unpaid_invoices%ROWTYPE;
    v_vp verified_payments%ROWTYPE;
    v_existing_vp verified_payments%ROWTYPE;
    v_paid_sum BIGINT;
    v_new_status TEXT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'verify_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- (a) lock the submission row, chapter-scoped.
    SELECT * INTO v_submission FROM payment_submissions
     WHERE id = p_submission_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'submission % not found in chapter %', p_submission_id, p_chapter_id;
    END IF;

    IF v_submission.status = 'approved' THEN
        -- Idempotent no-op: return the existing verified payment, flagged not-created.
        SELECT * INTO v_existing_vp FROM verified_payments
         WHERE submission_id = p_submission_id;
        RETURN to_jsonb(v_existing_vp) || jsonb_build_object('_created', false);
    END IF;
    IF v_submission.status = 'rejected' THEN
        RAISE EXCEPTION 'submission % was rejected and cannot be verified', p_submission_id;
    END IF;

    -- (b) lock the target invoice row.
    SELECT * INTO v_invoice FROM unpaid_invoices
     WHERE id = v_submission.invoice_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invoice % not found in chapter %', v_submission.invoice_id, p_chapter_id;
    END IF;

    -- (c) the verified payment. UNIQUE(submission_id) is the hard double-verify backstop.
    INSERT INTO verified_payments
        (chapter_id, member_id, invoice_id, submission_id, amount_cents, verified_by, verified_at)
    VALUES
        (p_chapter_id, v_submission.member_id, v_submission.invoice_id, v_submission.id,
         v_submission.claimed_amount_cents, p_actor_id, now())
    RETURNING * INTO v_vp;

    -- (d) the immutable receipt.
    INSERT INTO receipts
        (chapter_id, verified_payment_id, member_id, invoice_id, amount_cents, issued_by)
    VALUES
        (p_chapter_id, v_vp.id, v_vp.member_id, v_vp.invoice_id, v_vp.amount_cents, p_actor_id);

    -- (e) the PAYMENT_RECEIVED ledger entry (money in, signed positive).
    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'PAYMENT_RECEIVED', v_vp.amount_cents, v_vp.member_id,
            'verified_payments', v_vp.id, 'active');

    -- (f) approve the submission.
    UPDATE payment_submissions
       SET status = 'approved', reviewed_by = p_actor_id, reviewed_at = now()
     WHERE id = p_submission_id;

    -- (g) transition the invoice off total verified payments for it.
    SELECT COALESCE(SUM(amount_cents), 0) INTO v_paid_sum FROM verified_payments
     WHERE invoice_id = v_submission.invoice_id;

    IF v_paid_sum >= v_invoice.amount_cents THEN
        v_new_status := 'paid';
    ELSIF v_paid_sum > 0 THEN
        v_new_status := 'partially_paid';
    ELSE
        v_new_status := v_invoice.status;
    END IF;
    UPDATE unpaid_invoices SET status = v_new_status WHERE id = v_submission.invoice_id;

    -- (h) audit.
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'VERIFY_PAYMENT', p_actor_id, 'verified_payments', v_vp.id,
            jsonb_build_object('submission_id', v_submission.id, 'amount_cents', v_vp.amount_cents));

    -- (i) return, flagged created so the service notifies exactly once.
    v_result := to_jsonb(v_vp) || jsonb_build_object('_created', true);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'verify_payment', p_idempotency_key, v_vp.id,
                to_jsonb(v_vp) || jsonb_build_object('_created', false));
    END IF;

    RETURN v_result;
END;
$$;

-- ── reject a payment submission (no money, no ledger) ─────────────────────────
-- Idempotent: replaying an already-rejected submission returns it. Rejecting an
-- approved submission RAISES.
CREATE OR REPLACE FUNCTION tr_reject_payment(
    p_chapter_id UUID,
    p_submission_id UUID,
    p_actor_id UUID,
    p_reason TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_submission payment_submissions%ROWTYPE;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'reject_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_submission FROM payment_submissions
     WHERE id = p_submission_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'submission % not found in chapter %', p_submission_id, p_chapter_id;
    END IF;

    IF v_submission.status = 'approved' THEN
        RAISE EXCEPTION 'submission % is approved and cannot be rejected', p_submission_id;
    END IF;
    IF v_submission.status = 'rejected' THEN
        RETURN to_jsonb(v_submission);  -- idempotent no-op
    END IF;

    UPDATE payment_submissions
       SET status = 'rejected', reviewed_by = p_actor_id, reviewed_at = now()
     WHERE id = p_submission_id
    RETURNING * INTO v_submission;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'REJECT_PAYMENT', p_actor_id, 'payment_submissions', v_submission.id,
            jsonb_build_object('reason', p_reason));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'reject_payment', p_idempotency_key, v_submission.id, to_jsonb(v_submission));
    END IF;

    RETURN to_jsonb(v_submission);
END;
$$;
