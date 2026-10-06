-- RV-03-2: refund ownership is immutable because balances sum by member_id.
-- The shared freeze function receives its frozen columns as trigger arguments.
DROP TRIGGER IF EXISTS refunds_freeze ON refunds;
CREATE TRIGGER refunds_freeze
    BEFORE UPDATE ON refunds
    FOR EACH ROW EXECUTE FUNCTION tr_freeze_columns(
        'amount_cents', 'verified_payment_id', 'chapter_id', 'member_id');
