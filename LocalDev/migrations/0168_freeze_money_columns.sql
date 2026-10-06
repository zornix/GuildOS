-- F-031 · Amount and owner columns on money rows are frozen (decision D10).
--
-- The ledger stays a shadow log (report §10). Balances are computed from
-- verified_payments, finance_adjustments, refunds and unpaid_invoices, so those
-- rows may not have their amount or owner edited in place. Status transitions the
-- RPCs perform (invoice status, adjustment pending → active with approver, the
-- 0165 invoice_id clean-up) are untouched: no live function or Python path
-- updates a frozen column, and every FK on a frozen column is ON DELETE CASCADE
-- (a delete, never an UPDATE).

CREATE OR REPLACE FUNCTION tr_freeze_columns() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_col TEXT;
BEGIN
    FOREACH v_col IN ARRAY TG_ARGV LOOP
        IF to_jsonb(NEW) -> v_col IS DISTINCT FROM to_jsonb(OLD) -> v_col THEN
            RAISE EXCEPTION 'frozen: %.% cannot change after insert', TG_TABLE_NAME, v_col;
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS verified_payments_freeze ON verified_payments;
CREATE TRIGGER verified_payments_freeze
    BEFORE UPDATE ON verified_payments
    FOR EACH ROW EXECUTE FUNCTION tr_freeze_columns('amount_cents', 'member_id', 'chapter_id');

DROP TRIGGER IF EXISTS finance_adjustments_freeze ON finance_adjustments;
CREATE TRIGGER finance_adjustments_freeze
    BEFORE UPDATE ON finance_adjustments
    FOR EACH ROW EXECUTE FUNCTION tr_freeze_columns('delta_cents', 'member_id', 'chapter_id');

DROP TRIGGER IF EXISTS refunds_freeze ON refunds;
CREATE TRIGGER refunds_freeze
    BEFORE UPDATE ON refunds
    FOR EACH ROW EXECUTE FUNCTION tr_freeze_columns('amount_cents', 'verified_payment_id', 'chapter_id');

DROP TRIGGER IF EXISTS unpaid_invoices_freeze ON unpaid_invoices;
CREATE TRIGGER unpaid_invoices_freeze
    BEFORE UPDATE ON unpaid_invoices
    FOR EACH ROW EXECUTE FUNCTION tr_freeze_columns('amount_cents', 'member_id', 'chapter_id');
