-- Chunk E · Adjustment RPC: tr_create_adjustment (one atomic plpgsql txn).
-- Inserts the adjustment, appends a signed ADJUSTMENT_CREATED ledger entry, and
-- writes a CREATE_ADJUSTMENT audit row. reason/officer are mandatory (enforced by
-- the table's NOT NULL + non-empty CHECK; a NULL/blank value rolls the whole txn back).
-- A v2 in a later migration adds the optional over-threshold two-officer sign-off.

CREATE OR REPLACE FUNCTION tr_create_adjustment(
    p_chapter_id UUID,
    p_member_id UUID,
    p_kind TEXT,
    p_delta_cents BIGINT,
    p_reason TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_adj finance_adjustments%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'create_adjustment' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    INSERT INTO finance_adjustments (chapter_id, member_id, kind, delta_cents, reason, officer_id, status)
    VALUES (p_chapter_id, p_member_id, p_kind, p_delta_cents, p_reason, p_actor_id, 'active')
    RETURNING * INTO v_adj;

    -- Signed ledger entry (audit history only; balances are computed from operational rows).
    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'ADJUSTMENT_CREATED', p_delta_cents, p_member_id, 'finance_adjustments', v_adj.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_ADJUSTMENT', p_actor_id, 'finance_adjustments', v_adj.id,
            jsonb_build_object('kind', p_kind, 'delta_cents', p_delta_cents,
                               'member_id', p_member_id, 'reason', p_reason));

    v_result := to_jsonb(v_adj);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'create_adjustment', p_idempotency_key, v_adj.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
