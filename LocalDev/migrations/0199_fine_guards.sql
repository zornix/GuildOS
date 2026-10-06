-- F-004 / D20: keep one live fine per event and member. Paid duplicates
-- were refunded through tr_issue_refund before this migration.
DO $$
DECLARE
    r RECORD;
    v_two_paid INT;
BEGIN
    SELECT count(*) INTO v_two_paid FROM (
        SELECT 1 FROM unpaid_invoices
         WHERE kind = 'fine' AND source_event_id IS NOT NULL AND status = 'paid'
         GROUP BY source_event_id, member_id HAVING count(*) > 1) t;
    IF v_two_paid > 0 THEN
        RAISE EXCEPTION '0199: % event/member pairs have two PAID fines; refund one by hand before migrating', v_two_paid;
    END IF;

    FOR r IN
        SELECT id, chapter_id FROM (
            SELECT id, chapter_id, status,
                   row_number() OVER (PARTITION BY source_event_id, member_id
                                      ORDER BY (status = 'paid') DESC, created_at, id) AS rn
              FROM unpaid_invoices
             WHERE kind = 'fine' AND source_event_id IS NOT NULL AND status <> 'cancelled') x
         WHERE rn > 1 AND status IN ('unpaid', 'partially_paid')
    LOOP
        PERFORM tr_void_invoice(r.chapter_id, r.id, NULL, 'duplicate fine for the same event (migration 0199)', NULL);
    END LOOP;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fine_per_event_member
    ON unpaid_invoices (source_event_id, member_id)
    WHERE kind = 'fine' AND status <> 'cancelled' AND source_event_id IS NOT NULL;
