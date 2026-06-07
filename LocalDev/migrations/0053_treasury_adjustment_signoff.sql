-- Chunk E · Two-officer sign-off for large adjustments (Slice 9 governance).
-- Replaces tr_create_adjustment with a threshold-aware version and adds
-- tr_approve_adjustment. An adjustment whose magnitude meets the (configurable)
-- threshold is created 'pending' with NO ledger entry and NO balance effect; a
-- SECOND officer activates it via tr_approve_adjustment, which appends the
-- ADJUSTMENT_CREATED ledger entry at that point. Below-threshold adjustments are
-- 'active' immediately (threshold 0 disables the gate). Idempotent.

-- Drop the v1 (7-arg) signature so the new 8-arg version is unambiguous.
DROP FUNCTION IF EXISTS tr_create_adjustment(UUID, UUID, TEXT, BIGINT, TEXT, UUID, TEXT);

CREATE OR REPLACE FUNCTION tr_create_adjustment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_kind TEXT,
    p_delta_cents BIGINT,
    p_reason TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL,
    p_threshold_cents BIGINT DEFAULT 0
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_adj finance_adjustments%ROWTYPE;
    v_status TEXT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'create_adjustment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    -- Over-threshold adjustments wait for a second officer before taking effect.
    IF p_threshold_cents > 0 AND abs(p_delta_cents) >= p_threshold_cents THEN
        v_status := 'pending';
    ELSE
        v_status := 'active';
    END IF;

    INSERT INTO finance_adjustments (chapter_id, member_id, kind, delta_cents, reason, officer_id, status)
    VALUES (p_chapter_id, p_member_id, p_kind, p_delta_cents, p_reason, p_actor_id, v_status)
    RETURNING * INTO v_adj;

    -- The ledger entry (and therefore any balance effect) only exists once active.
    IF v_status = 'active' THEN
        INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
        VALUES (p_chapter_id, 'ADJUSTMENT_CREATED', p_delta_cents, p_member_id, 'finance_adjustments', v_adj.id, 'active');
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_ADJUSTMENT', p_actor_id, 'finance_adjustments', v_adj.id,
            jsonb_build_object('kind', p_kind, 'delta_cents', p_delta_cents,
                               'member_id', p_member_id, 'reason', p_reason, 'status', v_status));

    v_result := to_jsonb(v_adj);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'create_adjustment', p_idempotency_key, v_adj.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- Second-officer activation of a pending adjustment. The approver must differ from
-- the originating officer (true two-person control). Appends the deferred ledger entry.
CREATE OR REPLACE FUNCTION tr_approve_adjustment(
    p_chapter_id UUID,
    p_adjustment_id UUID,
    p_approver_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_adj finance_adjustments%ROWTYPE;
BEGIN
    SELECT * INTO v_adj FROM finance_adjustments
     WHERE id = p_adjustment_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'adjustment % not found in chapter %', p_adjustment_id, p_chapter_id;
    END IF;

    IF v_adj.status = 'active' THEN
        RETURN to_jsonb(v_adj);  -- idempotent no-op
    END IF;

    IF p_approver_id = v_adj.officer_id THEN
        RAISE EXCEPTION 'two-officer sign-off requires an officer other than %', v_adj.officer_id;
    END IF;

    UPDATE finance_adjustments
       SET status = 'active', approved_by = p_approver_id, approved_at = now()
     WHERE id = p_adjustment_id
    RETURNING * INTO v_adj;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'ADJUSTMENT_CREATED', v_adj.delta_cents, v_adj.member_id, 'finance_adjustments', v_adj.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_ADJUSTMENT', p_approver_id, 'finance_adjustments', v_adj.id,
            jsonb_build_object('event', 'approved', 'approved_by', p_approver_id));

    RETURN to_jsonb(v_adj);
END;
$$;
