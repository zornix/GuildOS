-- F-022 / F-023: permissions come from member_roles. The legacy members.role
-- column is display-only; assign/revoke of officer keep it in step.

-- Every legacy officer gets the member_roles row the resolver will now require.
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT m.chapter_id, m.id, 'officer'
  FROM members m
 WHERE m.role = 'officer'
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;

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
        -- Already assigned: idempotent success, return the existing row.
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

    DELETE FROM member_roles
     WHERE member_id = p_member_id AND role_key = p_role_key AND chapter_id = p_chapter_id
    RETURNING * INTO v_row;

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
