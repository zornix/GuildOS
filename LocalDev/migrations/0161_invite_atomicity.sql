-- au_invite_member — member row + setup code in one statement.
--
-- invite_members (api/auth/api/auth.py) ran these as two autocommitted
-- statements; a failure between them left a committed 'invited' row with no
-- redeemable code, and the officer's retry then failed on the duplicate email.
-- Same rationale as the au_* family in 0148: the psycopg shim cannot express
-- multi-statement atomicity, so the RPC is the transaction.
--
-- Called as one SELECT on an autocommit connection, so any error in the body
-- (the unique-email violation included) rolls back both inserts.

CREATE OR REPLACE FUNCTION au_invite_member(
    p_chapter_id     UUID,
    p_name           TEXT,
    p_email          TEXT,
    p_code_hash      TEXT,
    p_expires_at     TIMESTAMPTZ,
    p_sms_consent_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_member_id UUID;
BEGIN
    INSERT INTO members (chapter_id, name, email, role, status, sms_consent_at)
    VALUES (p_chapter_id, p_name, p_email, 'member', 'invited', p_sms_consent_at)
    RETURNING id INTO v_member_id;

    INSERT INTO member_setup_codes (chapter_id, member_id, code_hash, expires_at)
    VALUES (p_chapter_id, v_member_id, p_code_hash, p_expires_at);

    RETURN jsonb_build_object('member_id', v_member_id, 'expires_at', p_expires_at);
END;
$$;

-- Same lockdown as 0153: not PUBLIC-executable, and not for the Supabase
-- anon/authenticated roles where they exist (they do not on a bare Postgres).
REVOKE ALL ON FUNCTION au_invite_member(UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ) FROM PUBLIC;

DO $$
DECLARE
    v_roles TEXT;
BEGIN
    SELECT string_agg(quote_ident(rolname), ', ')
      INTO v_roles
      FROM pg_roles
     WHERE rolname IN ('anon', 'authenticated');

    IF v_roles IS NOT NULL THEN
        EXECUTE format(
            'REVOKE ALL ON FUNCTION au_invite_member(UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ) FROM %s',
            v_roles
        );
    END IF;
END
$$;
