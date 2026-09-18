-- 0160_outbox_retry_audit.sql — issue #90
--
-- An officer requeueing a failed message_outbox row is a trust-boundary
-- mutation and must leave an audit_logs row. The write itself is a plain insert
-- from api/announcements/services/outbox.py (single-row delivery bookkeeping,
-- not a financial multi-write — same reasoning as the drain's own updates), but
-- audit_logs.action is a closed catalog, so the new action has to be admitted
-- here first.

-- ── audit_logs action catalog extension (dual-format, pattern: 0152 §2) ──────

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['OUTBOX_RETRIED'];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        v_match := regexp_match(v_def, 'ARRAY\[(.+?)\]');
        IF v_match IS NOT NULL THEN
            FOREACH v_elem IN ARRAY string_to_array(v_match[1], ',') LOOP
                v_elem := trim(both '''' from regexp_replace(trim(v_elem), '::text$', ''));
                v_actions := v_actions || v_elem;
            END LOOP;
        ELSE
            v_match := regexp_match(v_def, '''(\{.+?\})''::text\[\]');
            IF v_match IS NOT NULL THEN
                v_actions := v_match[1]::text[];
            END IF;
        END IF;
    END IF;

    FOREACH v_elem IN ARRAY v_new LOOP
        IF NOT (v_elem = ANY (v_actions)) THEN
            v_actions := v_actions || v_elem;
        END IF;
    END LOOP;

    SELECT string_agg(quote_literal(a), ', ') INTO v_list FROM unnest(v_actions) AS a;

    EXECUTE 'ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check';
    EXECUTE 'ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check '
         || 'CHECK (action = ANY (ARRAY[' || v_list || ']::text[]))';
END $$;
