-- mem_set_legacy_role — promotion/demotion writes BOTH sides of "is an officer".
--
-- `PUT /members/{id}/role` used to write only `members.role`. Since 0147 §4
-- backfilled an `officer` row into `member_roles` for every then-active officer,
-- and `get_member_permissions` unions member_roles with LEGACY_ROLE_COMPAT, a
-- demotion left the member_roles grant standing: the member kept roles:assign,
-- treasury:refund:create, attendance:override and the rest indefinitely while
-- the roster showed them as an ordinary member.
--
-- One RPC so the two writes cannot half-apply (CLAUDE.md: trust-boundary
-- mutations go through plpgsql, with a chapter_id guard and an audit row).
--
-- Scoped to the 'officer' member_roles row ON PURPOSE: stackable roles granted
-- separately through rbac_assign_role (treasurer, secretary, chairs, ...) are
-- not this endpoint's to revoke and must survive a demotion.
--
-- Audit reuses the existing ASSIGN_ROLE / REVOKE_ROLE actions (0082 catalog);
-- the audit_logs action CHECK is frozen and is not widened here.

CREATE OR REPLACE FUNCTION mem_set_legacy_role(
    p_chapter_id UUID,
    p_member_id UUID,
    p_role TEXT,
    p_actor_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row members%ROWTYPE;
BEGIN
    UPDATE members
       SET role = p_role
     WHERE id = p_member_id
       AND chapter_id = p_chapter_id
    RETURNING * INTO v_row;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % is not in chapter %', p_member_id, p_chapter_id;
    END IF;

    IF p_role = 'officer' THEN
        INSERT INTO member_roles (chapter_id, member_id, role_key, assigned_by)
        VALUES (p_chapter_id, p_member_id, 'officer', p_actor_id)
        ON CONFLICT DO NOTHING;
    ELSE
        DELETE FROM member_roles
         WHERE chapter_id = p_chapter_id
           AND member_id = p_member_id
           AND role_key = 'officer';
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (
        p_chapter_id,
        CASE WHEN p_role = 'officer' THEN 'ASSIGN_ROLE' ELSE 'REVOKE_ROLE' END,
        p_actor_id,
        'members',
        p_member_id,
        jsonb_build_object('member_id', p_member_id, 'role_key', 'officer', 'legacy_role', p_role)
    );

    -- The endpoint's response shape, spelled out: to_jsonb(v_row) would hand the
    -- roster UI password_hash and token_version.
    RETURN jsonb_build_object(
        'id',         v_row.id,
        'chapter_id', v_row.chapter_id,
        'name',       v_row.name,
        'email',      v_row.email,
        'phone',      v_row.phone,
        'role',       v_row.role,
        'status',     v_row.status,
        'created_at', v_row.created_at
    );
END;
$$;

-- Never reachable from a browser-held token: this RPC bypasses RLS, so only the
-- backend's own connection may execute it (mirrors the auth-RPC exposure fix).
REVOKE ALL ON FUNCTION mem_set_legacy_role(UUID, UUID, TEXT, UUID) FROM PUBLIC;

-- anon/authenticated are Supabase-provided roles; CI runs bare Postgres where
-- they do not exist, so revoke only what is actually there.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION mem_set_legacy_role(UUID, UUID, TEXT, UUID) FROM anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION mem_set_legacy_role(UUID, UUID, TEXT, UUID) FROM authenticated';
    END IF;
END $$;
