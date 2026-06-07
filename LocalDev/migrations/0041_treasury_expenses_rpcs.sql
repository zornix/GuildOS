-- Chunk D · Expense RPCs: tr_create_expense, tr_invalidate_expense.

CREATE OR REPLACE FUNCTION tr_create_expense(
    p_chapter_id UUID,
    p_category TEXT,
    p_amount_cents BIGINT,
    p_description TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_expense chapter_expenses%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'create_expense' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    INSERT INTO chapter_expenses (chapter_id, category, amount_cents, status, description, created_by)
    VALUES (p_chapter_id, p_category, p_amount_cents, 'active', p_description, p_actor_id)
    RETURNING * INTO v_expense;

    -- Money out: signed negative so the active-ledger sum tracks the chapter balance.
    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
    VALUES (p_chapter_id, 'EXPENSE_APPROVED', -p_amount_cents, NULL, 'chapter_expenses', v_expense.id, 'active');

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'CREATE_EXPENSE', p_actor_id, 'chapter_expenses', v_expense.id,
            jsonb_build_object('category', p_category, 'amount_cents', p_amount_cents));

    v_result := to_jsonb(v_expense);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'create_expense', p_idempotency_key, v_expense.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- Invalidate: status active->invalidated, append a reversing EXPENSE_REVERSED entry
-- (reverses the original EXPENSE_APPROVED). Both the expense row and the original
-- ledger row are preserved (invariants 1 & 4). Idempotent.
CREATE OR REPLACE FUNCTION tr_invalidate_expense(
    p_chapter_id UUID,
    p_expense_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_expense chapter_expenses%ROWTYPE;
    v_original_entry UUID;
BEGIN
    SELECT * INTO v_expense FROM chapter_expenses
     WHERE id = p_expense_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'expense % not found in chapter %', p_expense_id, p_chapter_id;
    END IF;
    IF v_expense.status = 'invalidated' THEN
        RETURN to_jsonb(v_expense);  -- idempotent no-op
    END IF;

    UPDATE chapter_expenses SET status = 'invalidated' WHERE id = p_expense_id
    RETURNING * INTO v_expense;

    SELECT id INTO v_original_entry FROM big_ledger
     WHERE source_table = 'chapter_expenses' AND source_id = p_expense_id
       AND entry_type = 'EXPENSE_APPROVED'
     ORDER BY created_at ASC LIMIT 1;

    INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status, reverses_entry_id)
    VALUES (p_chapter_id, 'EXPENSE_REVERSED', v_expense.amount_cents, NULL,
            'chapter_expenses', v_expense.id, 'active', v_original_entry);

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'INVALIDATE_EXPENSE', p_actor_id, 'chapter_expenses', v_expense.id, '{}'::jsonb);

    RETURN to_jsonb(v_expense);
END;
$$;
