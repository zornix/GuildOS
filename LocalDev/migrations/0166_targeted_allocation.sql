-- F-032 · A payment goes to the invoice the member picked (decision D7).
--
-- tr_verify_payment_v2 (live body from 0124) allocated every submission
-- oldest-first, even one submitted against a specific invoice. Now, when the
-- submission names an invoice that is still open and belongs to the same member,
-- that invoice is covered first; the surplus (or everything, if the target is
-- already paid or cancelled) still goes oldest-first. Nothing else changes.

CREATE OR REPLACE FUNCTION tr_verify_payment_v2(
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
    v_vp verified_payments%ROWTYPE;
    v_existing_vp verified_payments%ROWTYPE;
    v_invoice unpaid_invoices%ROWTYPE;
    v_left BIGINT;
    v_remaining BIGINT;
    v_alloc BIGINT;
    v_allocated BIGINT := 0;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'verify_payment_v2' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- (a) lock the submission, chapter-scoped (0031 pattern).
    SELECT * INTO v_submission FROM payment_submissions
     WHERE id = p_submission_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'submission % not found in chapter %', p_submission_id, p_chapter_id;
    END IF;

    IF v_submission.status = 'approved' THEN
        SELECT * INTO v_existing_vp FROM verified_payments WHERE submission_id = p_submission_id;
        RETURN to_jsonb(v_existing_vp) || jsonb_build_object('_created', false);
    END IF;
    IF v_submission.status = 'rejected' THEN
        RAISE EXCEPTION 'submission % was rejected and cannot be verified', p_submission_id;
    END IF;

    -- (b) the verified payment. invoice_id is NULL: v2 attribution lives in
    -- payment_allocations. UNIQUE(submission_id) is the double-verify backstop.
    INSERT INTO verified_payments
        (chapter_id, member_id, invoice_id, submission_id, amount_cents, verified_by, verified_at)
    VALUES
        (p_chapter_id, v_submission.member_id, NULL, v_submission.id,
         v_submission.claimed_amount_cents, p_actor_id, now())
    RETURNING * INTO v_vp;

    -- (c) the immutable receipt.
    INSERT INTO receipts
        (chapter_id, verified_payment_id, member_id, invoice_id, amount_cents, issued_by)
    VALUES
        (p_chapter_id, v_vp.id, v_vp.member_id, NULL, v_vp.amount_cents, p_actor_id);

    -- (d) PAYMENT_RECEIVED ledger entry (money in, positive).
    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'PAYMENT_RECEIVED', v_vp.amount_cents, v_vp.member_id,
            'verified_payments', v_vp.id, 'active');

    -- (e) approve the submission.
    UPDATE payment_submissions
       SET status = 'approved', reviewed_by = p_actor_id, reviewed_at = now()
     WHERE id = p_submission_id;

    v_left := v_vp.amount_cents;

    -- (f0) D7: the invoice the submission names comes first while it is still
    -- open and belongs to the same member; otherwise everything goes oldest-first.
    IF v_submission.invoice_id IS NOT NULL THEN
        -- lock the member's open invoices in the loop's order (no lock-order deadlock)
        PERFORM 1 FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id
           AND member_id = v_submission.member_id
           AND status IN ('unpaid', 'partially_paid')
         ORDER BY created_at ASC, id ASC
         FOR UPDATE;

        SELECT * INTO v_invoice FROM unpaid_invoices
         WHERE id = v_submission.invoice_id
           AND chapter_id = p_chapter_id
           AND member_id = v_submission.member_id
           AND status IN ('unpaid', 'partially_paid');
        IF FOUND THEN
            v_alloc := LEAST(v_left, tr_invoice_remaining_cents(v_invoice.id));
            IF v_alloc > 0 THEN
                INSERT INTO payment_allocations
                    (chapter_id, verified_payment_id, invoice_id, amount_cents, allocated_by)
                VALUES
                    (p_chapter_id, v_vp.id, v_invoice.id, v_alloc, p_actor_id);
                v_left := v_left - v_alloc;
                v_allocated := v_allocated + v_alloc;
            END IF;
            PERFORM tr_refresh_invoice_status(v_invoice.id);
        END IF;
    END IF;

    -- (f) allocate the rest OLDEST-FIRST across the member's other open invoices.
    FOR v_invoice IN
        SELECT * FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id
           AND member_id = v_submission.member_id
           AND status IN ('unpaid', 'partially_paid')
           AND id IS DISTINCT FROM v_submission.invoice_id
         ORDER BY created_at ASC, id ASC
         FOR UPDATE
    LOOP
        EXIT WHEN v_left <= 0;
        v_remaining := tr_invoice_remaining_cents(v_invoice.id);
        IF v_remaining <= 0 THEN
            PERFORM tr_refresh_invoice_status(v_invoice.id);
            CONTINUE;
        END IF;

        v_alloc := LEAST(v_remaining, v_left);
        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents, allocated_by)
        VALUES
            (p_chapter_id, v_vp.id, v_invoice.id, v_alloc, p_actor_id);
        v_left := v_left - v_alloc;
        v_allocated := v_allocated + v_alloc;

        PERFORM tr_refresh_invoice_status(v_invoice.id);
    END LOOP;

    -- (g) audit.
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'VERIFY_PAYMENT', p_actor_id, 'verified_payments', v_vp.id,
            jsonb_build_object('submission_id', v_submission.id,
                               'amount_cents', v_vp.amount_cents,
                               'allocated_cents', v_allocated,
                               'leftover_cents', v_left));

    v_result := to_jsonb(v_vp)
        || jsonb_build_object('_created', true, 'allocated_cents', v_allocated, 'leftover_cents', v_left);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'verify_payment_v2', p_idempotency_key, v_vp.id,
                to_jsonb(v_vp) || jsonb_build_object('_created', false,
                                                     'allocated_cents', v_allocated,
                                                     'leftover_cents', v_left));
    END IF;

    RETURN v_result;
END;
$$;
