-- F-023 / D8: chapter creators are admins; only an admin grants or revokes
-- admin and president; a chapter keeps at least one admin who can still log in.

-- Every existing chapter gets one admin: its earliest officer who can still log in.
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT DISTINCT ON (m.chapter_id) m.chapter_id, m.id, 'admin'
  FROM members m
  JOIN member_roles mr
    ON mr.member_id = m.id AND mr.chapter_id = m.chapter_id AND mr.role_key = 'officer'
 WHERE m.status IN ('active', 'invited')
   AND NOT EXISTS (SELECT 1 FROM member_roles a
                    WHERE a.chapter_id = m.chapter_id AND a.role_key = 'admin')
 ORDER BY m.chapter_id, m.created_at, m.id
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;

CREATE OR REPLACE FUNCTION ch_create_chapter(
    p_name          TEXT,
    p_organization  TEXT,
    p_school        TEXT,
    p_officer_name  TEXT,
    p_officer_email TEXT,
    p_officer_phone TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_chapter_id UUID;
    v_member_id  UUID;
BEGIN
    -- Never upsert: an existing chapter or member is a 409, not a merge.
    IF EXISTS (SELECT 1 FROM chapters WHERE lower(name) = lower(p_name)) THEN
        RAISE EXCEPTION 'chapter_name_taken';
    END IF;
    IF EXISTS (SELECT 1 FROM members WHERE lower(email) = lower(p_officer_email)) THEN
        RAISE EXCEPTION 'officer_email_taken';
    END IF;

    INSERT INTO chapters (name, organization, school)
    VALUES (p_name, p_organization, p_school)
    RETURNING id INTO v_chapter_id;

    -- status='invited', no password_hash: the officer claims the account by
    -- redeeming the setup code, so knowing the address is not enough to take it.
    INSERT INTO members (chapter_id, name, email, phone, role, status)
    VALUES (v_chapter_id, p_officer_name, lower(p_officer_email), p_officer_phone,
            'officer', 'invited')
    RETURNING id INTO v_member_id;

    -- Mirror into RBAC when the catalog is present (provision_chapter.py skips
    -- it on databases that predate 0083; same tolerance here).
    INSERT INTO member_roles (chapter_id, member_id, role_key)
    SELECT v_chapter_id, v_member_id, 'officer'
     WHERE EXISTS (SELECT 1 FROM roles WHERE key = 'officer')
    ON CONFLICT DO NOTHING;

    INSERT INTO member_roles (chapter_id, member_id, role_key)
    SELECT v_chapter_id, v_member_id, 'admin'
     WHERE EXISTS (SELECT 1 FROM roles WHERE key = 'admin');

    RETURN jsonb_build_object(
        'chapter_id',    v_chapter_id,
        'officer_id',    v_member_id,
        'officer_email', lower(p_officer_email)
    );
END;
$$;

CREATE OR REPLACE FUNCTION rbac_assign_role(
    p_chapter_id UUID,
    p_member_id UUID,
    p_role_key TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row member_roles%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'rbac_assign_role' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF p_role_key IN ('admin', 'president')
       AND NOT EXISTS (
            SELECT 1 FROM member_roles
             WHERE chapter_id = p_chapter_id AND member_id = p_actor_id AND role_key = 'admin')
    THEN
        RAISE EXCEPTION 'rbac_ceiling: only an admin may grant or revoke %', p_role_key;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM roles WHERE key = p_role_key) THEN
        RAISE EXCEPTION 'unknown role %', p_role_key;
    END IF;

    INSERT INTO member_roles (chapter_id, member_id, role_key, assigned_by)
    VALUES (p_chapter_id, p_member_id, p_role_key, p_actor_id)
    ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
    RETURNING * INTO v_row;

    IF p_role_key = 'officer' THEN
        UPDATE members SET role = 'officer'
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND role <> 'officer';
    END IF;

    IF v_row.id IS NULL THEN
        SELECT * INTO v_row FROM member_roles
         WHERE member_id = p_member_id AND role_key = p_role_key AND chapter_id = p_chapter_id;
    ELSE
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'ASSIGN_ROLE', p_actor_id, 'member_roles', v_row.id,
                jsonb_build_object('member_id', p_member_id, 'role_key', p_role_key));
    END IF;

    v_result := to_jsonb(v_row);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'rbac_assign_role', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION rbac_revoke_role(
    p_chapter_id UUID,
    p_member_id UUID,
    p_role_key TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_row member_roles%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'rbac_revoke_role' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members WHERE id = p_member_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF p_role_key IN ('admin', 'president')
       AND NOT EXISTS (
            SELECT 1 FROM member_roles
             WHERE chapter_id = p_chapter_id AND member_id = p_actor_id AND role_key = 'admin')
    THEN
        RAISE EXCEPTION 'rbac_ceiling: only an admin may grant or revoke %', p_role_key;
    END IF;

    DELETE FROM member_roles
     WHERE member_id = p_member_id AND role_key = p_role_key AND chapter_id = p_chapter_id
    RETURNING * INTO v_row;

    IF v_row.id IS NOT NULL AND p_role_key = 'admin' AND NOT EXISTS (
        SELECT 1
          FROM member_roles mr
          JOIN members m ON m.id = mr.member_id
         WHERE mr.chapter_id = p_chapter_id
           AND mr.role_key = 'admin'
           AND m.status IN ('active', 'invited')
    ) THEN
        RAISE EXCEPTION 'rbac_last_admin: chapter % must keep at least one admin', p_chapter_id;
    END IF;

    IF v_row.id IS NOT NULL AND p_role_key = 'officer' THEN
        UPDATE members SET role = 'member'
         WHERE id = p_member_id AND chapter_id = p_chapter_id AND role = 'officer';
    END IF;

    IF v_row.id IS NOT NULL THEN
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (p_chapter_id, 'REVOKE_ROLE', p_actor_id, 'member_roles', v_row.id,
                jsonb_build_object('member_id', p_member_id, 'role_key', p_role_key));
    END IF;

    v_result := jsonb_build_object('revoked', v_row.id IS NOT NULL,
                                   'member_id', p_member_id, 'role_key', p_role_key);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'rbac_revoke_role', p_idempotency_key, v_row.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;
