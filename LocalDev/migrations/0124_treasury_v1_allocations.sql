-- TREASURY V1 · Verification + allocation (spec §5, decision #2).
--
-- payment_allocations is the append-only attribution of a verified payment to
-- invoices. Amounts are ALWAYS positive; a correction row sets
-- reverses_allocation_id and SUBTRACTS in the net. UPDATE/DELETE are blocked.
--
-- tr_verify_payment_v2 verifies BOTH invoice-targeted and balance-level
-- submissions: verified_payments + receipts + PAYMENT_RECEIVED ledger (0031
-- pattern), then allocates the amount across the member's open invoices
-- OLDEST-FIRST. v2 verified payments carry invoice_id NULL — their invoice
-- attribution lives exclusively in payment_allocations, so an invoice's
-- remaining = amount_cents − direct legacy verified_payments − net allocations.
--
-- tr_reallocate_payment is the treasurer override: appends reversal rows for
-- every live allocation of the payment, appends the new allocation set
-- (total ≤ verified amount), recomputes invoice statuses, audits with reason.

-- v2 verified payments / receipts are not pinned to one invoice.
ALTER TABLE verified_payments ALTER COLUMN invoice_id DROP NOT NULL;
ALTER TABLE receipts ALTER COLUMN invoice_id DROP NOT NULL;

-- ── payment_allocations ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payment_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    verified_payment_id UUID NOT NULL REFERENCES verified_payments(id) ON DELETE CASCADE,
    invoice_id UUID NOT NULL REFERENCES unpaid_invoices(id) ON DELETE CASCADE,
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    reverses_allocation_id UUID NULL REFERENCES payment_allocations(id),
    allocated_by UUID REFERENCES members(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_payment_allocations_chapter_id ON payment_allocations(chapter_id);
CREATE INDEX IF NOT EXISTS ix_payment_allocations_vp_id ON payment_allocations(verified_payment_id);
CREATE INDEX IF NOT EXISTS ix_payment_allocations_invoice_id ON payment_allocations(invoice_id);
CREATE INDEX IF NOT EXISTS ix_payment_allocations_reverses
    ON payment_allocations(reverses_allocation_id) WHERE reverses_allocation_id IS NOT NULL;

DROP TRIGGER IF EXISTS payment_allocations_no_delete ON payment_allocations;
CREATE TRIGGER payment_allocations_no_delete
    BEFORE DELETE ON payment_allocations
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS payment_allocations_no_update ON payment_allocations;
CREATE TRIGGER payment_allocations_no_update
    BEFORE UPDATE ON payment_allocations
    FOR EACH ROW EXECUTE FUNCTION tr_block_audit_log_mutation();

ALTER TABLE payment_allocations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payment_allocations_select ON payment_allocations;
CREATE POLICY payment_allocations_select ON payment_allocations
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM verified_payments vp
            WHERE vp.id = payment_allocations.verified_payment_id
              AND vp.member_id = treasury_request_member_id()
        )
        OR treasury_has_capability(chapter_id, 'payment:review')
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

-- ── helpers ───────────────────────────────────────────────────────────────────
-- Net cents allocated to an invoice (originals add, reversal rows subtract).
CREATE OR REPLACE FUNCTION tr_net_allocated_cents(p_invoice_id UUID)
RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(SUM(
        CASE WHEN pa.reverses_allocation_id IS NULL THEN pa.amount_cents
             ELSE -pa.amount_cents END), 0)
    FROM payment_allocations pa
    WHERE pa.invoice_id = p_invoice_id
$$;

-- Remaining = amount − direct legacy verified payments − net allocations.
CREATE OR REPLACE FUNCTION tr_invoice_remaining_cents(p_invoice_id UUID)
RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT ui.amount_cents
         - COALESCE((SELECT SUM(vp.amount_cents) FROM verified_payments vp
                      WHERE vp.invoice_id = ui.id), 0)
         - tr_net_allocated_cents(ui.id)
    FROM unpaid_invoices ui
    WHERE ui.id = p_invoice_id
$$;

-- Recompute one invoice's status off coverage (cancelled rows are left alone).
CREATE OR REPLACE FUNCTION tr_refresh_invoice_status(p_invoice_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice unpaid_invoices%ROWTYPE;
    v_remaining BIGINT;
    v_new_status TEXT;
BEGIN
    SELECT * INTO v_invoice FROM unpaid_invoices WHERE id = p_invoice_id FOR UPDATE;
    IF NOT FOUND OR v_invoice.status = 'cancelled' THEN
        RETURN;
    END IF;

    v_remaining := tr_invoice_remaining_cents(p_invoice_id);
    IF v_remaining <= 0 THEN
        v_new_status := 'paid';
    ELSIF v_remaining < v_invoice.amount_cents THEN
        v_new_status := 'partially_paid';
    ELSE
        v_new_status := 'unpaid';
    END IF;

    IF v_new_status <> v_invoice.status THEN
        UPDATE unpaid_invoices SET status = v_new_status WHERE id = p_invoice_id;
    END IF;
END;
$$;

-- ── tr_verify_payment_v2 ──────────────────────────────────────────────────────
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

    -- (f) allocate OLDEST-FIRST across the member's open invoices.
    v_left := v_vp.amount_cents;
    FOR v_invoice IN
        SELECT * FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id
           AND member_id = v_submission.member_id
           AND status IN ('unpaid', 'partially_paid')
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

-- ── tr_reallocate_payment: treasurer override, append-only ────────────────────
-- p_allocations: jsonb array of {invoice_id, amount_cents}; total ≤ the verified
-- amount (a smaller total leaves the rest as member credit).
CREATE OR REPLACE FUNCTION tr_reallocate_payment(
    p_chapter_id UUID,
    p_verified_payment_id UUID,
    p_allocations JSONB,
    p_actor_id UUID,
    p_reason TEXT,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_vp verified_payments%ROWTYPE;
    v_row payment_allocations%ROWTYPE;
    v_item JSONB;
    v_invoice unpaid_invoices%ROWTYPE;
    v_invoice_id UUID;
    v_amount BIGINT;
    v_total BIGINT := 0;
    v_affected UUID[] := ARRAY[]::UUID[];
    v_id UUID;
    v_result JSONB;
BEGIN
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason is required to reallocate a payment';
    END IF;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'reallocate_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_allocations IS NULL OR jsonb_typeof(p_allocations) <> 'array' THEN
        RAISE EXCEPTION 'p_allocations must be a JSON array';
    END IF;

    SELECT * INTO v_vp FROM verified_payments
     WHERE id = p_verified_payment_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'verified payment % not found in chapter %', p_verified_payment_id, p_chapter_id;
    END IF;

    SELECT COALESCE(SUM((item->>'amount_cents')::BIGINT), 0) INTO v_total
      FROM jsonb_array_elements(p_allocations) AS item;
    IF v_total > v_vp.amount_cents THEN
        RAISE EXCEPTION 'allocations total (%) exceeds the verified amount (%)', v_total, v_vp.amount_cents;
    END IF;

    -- (a) append a reversal for every live (un-reversed, original) allocation.
    FOR v_row IN
        SELECT * FROM payment_allocations pa
         WHERE pa.verified_payment_id = p_verified_payment_id
           AND pa.reverses_allocation_id IS NULL
           AND NOT EXISTS (
                SELECT 1 FROM payment_allocations r
                 WHERE r.reverses_allocation_id = pa.id)
         ORDER BY pa.created_at, pa.id
    LOOP
        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents,
             reverses_allocation_id, allocated_by, note)
        VALUES
            (p_chapter_id, p_verified_payment_id, v_row.invoice_id, v_row.amount_cents,
             v_row.id, p_actor_id, p_reason);
        v_affected := array_append(v_affected, v_row.invoice_id);
    END LOOP;

    -- (b) append the new allocation set.
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_allocations)
    LOOP
        v_invoice_id := (v_item->>'invoice_id')::UUID;
        v_amount := (v_item->>'amount_cents')::BIGINT;

        SELECT * INTO v_invoice FROM unpaid_invoices
         WHERE id = v_invoice_id AND chapter_id = p_chapter_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'invoice % not found in chapter %', v_invoice_id, p_chapter_id;
        END IF;
        IF v_invoice.member_id <> v_vp.member_id THEN
            RAISE EXCEPTION 'invoice % does not belong to the paying member', v_invoice_id;
        END IF;
        IF v_invoice.status = 'cancelled' THEN
            RAISE EXCEPTION 'cannot allocate to a cancelled invoice (%)', v_invoice_id;
        END IF;

        INSERT INTO payment_allocations
            (chapter_id, verified_payment_id, invoice_id, amount_cents, allocated_by, note)
        VALUES
            (p_chapter_id, p_verified_payment_id, v_invoice_id, v_amount, p_actor_id, p_reason);
        v_affected := array_append(v_affected, v_invoice_id);
    END LOOP;

    -- (c) recompute every affected invoice's status.
    FOREACH v_id IN ARRAY v_affected
    LOOP
        PERFORM tr_refresh_invoice_status(v_id);
    END LOOP;

    -- (d) audit (action enum is frozen — VERIFY_PAYMENT + op marker; see 0122 note).
    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'VERIFY_PAYMENT', p_actor_id, 'verified_payments', p_verified_payment_id,
            jsonb_build_object('op', 'reallocate_payment', 'reason', p_reason,
                               'allocations', p_allocations));

    v_result := jsonb_build_object(
        'verified_payment_id', p_verified_payment_id,
        'allocated_total_cents', v_total,
        'leftover_cents', v_vp.amount_cents - v_total);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'reallocate_payment', p_idempotency_key, p_verified_payment_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
