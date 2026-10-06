-- F-023 follow-up (review of stream 02): concurrent admin revocations could
-- remove every admin (write skew). 0164 is applied and frozen, so the lock
-- goes in a new file. Body otherwise identical to 0164's rbac_revoke_role.

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

    -- Two admins stepping down at once must not both pass the last-admin check
    -- below: serialize admin revocations per chapter on the chapter row.
    IF p_role_key = 'admin' THEN
        PERFORM 1 FROM chapters WHERE id = p_chapter_id FOR UPDATE;
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
