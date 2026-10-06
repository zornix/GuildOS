-- F-031 follow-up: 0168 created tr_freeze_columns() with the default EXECUTE
-- grant to PUBLIC. Postgres never runs a trigger function outside a trigger, so
-- the exposure is nil, but tests/auth/test_rpc_privileges.py pins "no repo
-- function in public is PUBLIC-executable". 0168 is applied and frozen, so the
-- revoke lives here. Numbered after the wave 2-3 ranges (0176-0202) on purpose.

REVOKE ALL ON FUNCTION tr_freeze_columns() FROM PUBLIC;

DO $$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format('REVOKE ALL ON FUNCTION tr_freeze_columns() FROM %I', v_role);
        END IF;
    END LOOP;
END $$;
