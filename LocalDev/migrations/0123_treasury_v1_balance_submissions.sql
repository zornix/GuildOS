-- TREASURY V1 · Balance-level payment submissions (spec §5 Payments):
-- a member submits amount + method + evidence against their OVERALL balance, so
-- payment_submissions.invoice_id becomes nullable; method gains 'check';
-- payment_evidence stores uploaded proof bytes (≤ 2 MiB, append-only).

-- ── payment_submissions: balance-level rows have NULL invoice_id ──────────────
ALTER TABLE payment_submissions ALTER COLUMN invoice_id DROP NOT NULL;

ALTER TABLE payment_submissions DROP CONSTRAINT IF EXISTS payment_submissions_method_check;
ALTER TABLE payment_submissions ADD CONSTRAINT payment_submissions_method_check
    CHECK (method IN ('venmo', 'zelle', 'cash', 'bank_transfer', 'check'));

-- ── payment_evidence: append-only proof blobs ─────────────────────────────────
CREATE TABLE IF NOT EXISTS payment_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    submission_id UUID NOT NULL REFERENCES payment_submissions(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL,
    data BYTEA NOT NULL,
    size_bytes INT NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 2 * 1024 * 1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_payment_evidence_chapter_id ON payment_evidence(chapter_id);
CREATE INDEX IF NOT EXISTS ix_payment_evidence_submission_id ON payment_evidence(submission_id);

DROP TRIGGER IF EXISTS payment_evidence_no_delete ON payment_evidence;
CREATE TRIGGER payment_evidence_no_delete
    BEFORE DELETE ON payment_evidence
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS payment_evidence_no_update ON payment_evidence;
CREATE TRIGGER payment_evidence_no_update
    BEFORE UPDATE ON payment_evidence
    FOR EACH ROW EXECUTE FUNCTION tr_block_audit_log_mutation();

ALTER TABLE payment_evidence ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payment_evidence_select ON payment_evidence;
CREATE POLICY payment_evidence_select ON payment_evidence
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM payment_submissions ps
            WHERE ps.id = payment_evidence.submission_id
              AND ps.member_id = treasury_request_member_id()
        )
        OR treasury_has_capability(chapter_id, 'payment:review')
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

-- ── tr_submit_balance_payment: pending submission, NULL invoice ───────────────
-- No money moves on submission (no ledger). Tenant guard: the member must belong
-- to the chapter (0080 pattern).
CREATE OR REPLACE FUNCTION tr_submit_balance_payment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_claimed_amount_cents BIGINT,
    p_method TEXT,
    p_proof_ref TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_submission payment_submissions%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'submit_balance_payment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    INSERT INTO payment_submissions
        (chapter_id, member_id, invoice_id, claimed_amount_cents, method, proof_ref, status)
    VALUES
        (p_chapter_id, p_member_id, NULL, p_claimed_amount_cents, p_method, p_proof_ref, 'pending')
    RETURNING * INTO v_submission;

    v_result := to_jsonb(v_submission);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'submit_balance_payment', p_idempotency_key, v_submission.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
