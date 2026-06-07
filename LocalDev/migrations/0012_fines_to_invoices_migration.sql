-- Chunk A · Fines integration (§7.8): make unpaid_invoices(kind=fine) the single
-- source of truth. Migrate every legacy fine into an invoice (+ ledger + a verified
-- payment for paid fines), then FREEZE the fines table read-only.

DO $$
DECLARE
    f RECORD;
    v_invoice_id UUID;
    v_amount_cents BIGINT;
    v_status TEXT;
BEGIN
    FOR f IN
        SELECT * FROM fines
        WHERE amount > 0
          AND NOT EXISTS (
            SELECT 1 FROM unpaid_invoices ui WHERE ui.legacy_fine_id = fines.id
          )
    LOOP
        v_amount_cents := round(f.amount * 100)::BIGINT;
        v_status := CASE f.status
            WHEN 'paid' THEN 'paid'
            WHEN 'waived' THEN 'cancelled'
            ELSE 'unpaid'
        END;

        INSERT INTO unpaid_invoices
            (chapter_id, member_id, kind, amount_cents, status, description, legacy_fine_id, created_at)
        VALUES
            (f.chapter_id, f.member_id, 'fine', v_amount_cents, v_status,
             COALESCE(f.reason, 'Migrated fine'), f.id, f.issued_at)
        RETURNING id INTO v_invoice_id;

        -- Ledger: the invoice was created (keeps Chunk G rebuild parity intact).
        INSERT INTO big_ledger
            (chapter_id, created_at, entry_type, amount_cents, member_id, source_table, source_id, status)
        VALUES
            (f.chapter_id, f.issued_at, 'INVOICE_CREATED', v_amount_cents, f.member_id,
             'unpaid_invoices', v_invoice_id, 'active');

        IF f.status = 'paid' THEN
            INSERT INTO verified_payments
                (chapter_id, member_id, invoice_id, submission_id, amount_cents, verified_by, verified_at, created_at)
            VALUES
                (f.chapter_id, f.member_id, v_invoice_id, NULL, v_amount_cents,
                 NULL, COALESCE(f.paid_at, f.issued_at), COALESCE(f.paid_at, f.issued_at));

            INSERT INTO big_ledger
                (chapter_id, created_at, entry_type, amount_cents, member_id, source_table, source_id, status)
            VALUES
                (f.chapter_id, COALESCE(f.paid_at, f.issued_at), 'PAYMENT_RECEIVED', v_amount_cents,
                 f.member_id, 'unpaid_invoices', v_invoice_id, 'active');

        ELSIF f.status = 'waived' THEN
            INSERT INTO big_ledger
                (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
            VALUES
                (f.chapter_id, 'CANCEL_INVOICE', -v_amount_cents, f.member_id,
                 'unpaid_invoices', v_invoice_id, 'active');
        END IF;
    END LOOP;
END $$;

-- ── Freeze: fines become read-only. New fines are created as invoices instead. ─
CREATE OR REPLACE FUNCTION tr_block_all_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'fines is frozen (read-only); fines are recorded as unpaid_invoices(kind=fine)';
END;
$$;

DROP TRIGGER IF EXISTS fines_frozen ON fines;
CREATE TRIGGER fines_frozen
    BEFORE INSERT OR UPDATE OR DELETE ON fines
    FOR EACH ROW EXECUTE FUNCTION tr_block_all_mutation();
