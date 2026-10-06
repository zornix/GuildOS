-- F-005: credential transitions revoke outstanding codes and sessions.

CREATE OR REPLACE FUNCTION au_set_password(
    p_member_id UUID,
    p_password_hash TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_version INT;
BEGIN
    UPDATE members
       SET password_hash = p_password_hash,
           token_version = token_version + 1
     WHERE id = p_member_id
    RETURNING token_version INTO v_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % not found', p_member_id;
    END IF;

    UPDATE member_setup_codes SET used_at = now()
     WHERE member_id = p_member_id AND used_at IS NULL;

    RETURN jsonb_build_object('member_id', p_member_id, 'token_version', v_version);
END;
$$;

CREATE OR REPLACE FUNCTION au_bump_token_version(
    p_chapter_id UUID,
    p_member_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_version INT;
BEGIN
    UPDATE members
       SET token_version = token_version + 1
     WHERE id = p_member_id AND chapter_id = p_chapter_id
    RETURNING token_version INTO v_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % not found in chapter %', p_member_id, p_chapter_id;
    END IF;

    UPDATE member_setup_codes SET used_at = now()
     WHERE member_id = p_member_id AND used_at IS NULL;

    RETURN jsonb_build_object('member_id', p_member_id, 'token_version', v_version);
END;
$$;

CREATE OR REPLACE FUNCTION au_consume_setup_code(
    p_chapter_id UUID,
    p_code_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_member_id UUID;
    v_version INT;
BEGIN
    UPDATE member_setup_codes
       SET used_at = now()
     WHERE id = p_code_id
       AND chapter_id = p_chapter_id
       AND used_at IS NULL
       AND expires_at > now()
    RETURNING member_id INTO v_member_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('claimed', false, 'member_id', NULL);
    END IF;

    UPDATE members
       SET status = 'active'
     WHERE id = v_member_id
       AND chapter_id = p_chapter_id
       AND status = 'invited';

    UPDATE members SET token_version = token_version + 1
     WHERE id = v_member_id
    RETURNING token_version INTO v_version;

    UPDATE member_setup_codes SET used_at = now()
     WHERE member_id = v_member_id AND used_at IS NULL;

    RETURN jsonb_build_object('claimed', true, 'member_id', v_member_id,
                              'token_version', v_version);
END;
$$;
