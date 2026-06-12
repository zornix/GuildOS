-- RBAC seed (role catalog, permission catalog, default role→permission matrix),
-- legacy-role backfill, and the role assignment/revocation RPCs.
--
-- The matrix here is the durable default; docs/services/permissions-matrix.md is
-- the human-readable companion. scripts/seed.py re-seeds the same data for the
-- local demo database.

-- ── Role catalog ──────────────────────────────────────────────────────────────
INSERT INTO roles (key, label) VALUES
    ('president',           'President'),
    ('vice_president',      'Vice President'),
    ('treasurer',           'Treasurer'),
    ('secretary',           'Secretary'),
    ('risk_chair',          'Risk Chair'),
    ('social_chair',        'Social Chair'),
    ('recruitment_chair',   'Recruitment Chair'),
    ('brotherhood_chair',   'Brotherhood Chair'),
    ('philanthropy_chair',  'Philanthropy Chair'),
    ('standards_chair',     'Standards Chair'),
    ('new_member_educator', 'New Member Educator'),
    ('alumni_advisor',      'Alumni Advisor'),
    ('officer',             'Officer'),
    ('member',              'Member'),
    ('admin',               'Admin')
ON CONFLICT (key) DO NOTHING;

-- ── Permission catalog ────────────────────────────────────────────────────────
INSERT INTO permissions (key, description) VALUES
    ('calendar:event:create',        'Create events'),
    ('calendar:event:update',        'Update events'),
    ('calendar:event:delete',        'Delete events'),
    ('calendar:officer:view',        'View officer-visibility events'),
    ('attendance:checkin:create',    'Open check-in sessions / links'),
    ('attendance:override',          'Manually override attendance'),
    ('attendance:excuse:review',     'Review absence excuses'),
    ('treasury:invoice:create',      'Create invoices'),
    ('treasury:payment:verify',      'Verify payment submissions'),
    ('treasury:budget:view',         'View budgets'),
    ('treasury:audit:view',          'View treasury audit trail'),
    ('tasks:create',                 'Create tasks'),
    ('tasks:assign',                 'Assign tasks to members'),
    ('tasks:complete',               'Complete tasks (own, unless tasks:review)'),
    ('tasks:review',                 'Review / complete any chapter task'),
    ('announcements:create',         'Draft announcements'),
    ('announcements:send',           'Send announcements'),
    ('standing:view_all',            'View all member standings'),
    ('standing:update',              'Update standing statuses / reason codes'),
    ('recruitment:pipeline:view',    'View recruitment pipeline'),
    ('recruitment:pipeline:update',  'Update recruitment pipeline'),
    ('bylaws:query',                 'Query bylaws'),
    ('bylaws:admin',                 'Manage bylaws documents'),
    ('nl_controller:execute',        'Submit natural-language commands'),
    ('nl_controller:approve',        'Approve / reject command requests'),
    ('roles:assign',                 'Assign and revoke roles (admin only)')
ON CONFLICT (key) DO NOTHING;

-- ── Default role→permission matrix ────────────────────────────────────────────
-- admin: every permission, including roles:assign.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'admin', p.key FROM permissions p
ON CONFLICT DO NOTHING;

-- officer: the legacy require_officer surface, expressed as granular permissions.
-- The compatibility resolver maps members.role='officer' onto this role.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'officer', x.perm FROM (VALUES
    ('calendar:event:create'), ('calendar:event:update'), ('calendar:event:delete'),
    ('calendar:officer:view'),
    ('attendance:checkin:create'), ('attendance:override'), ('attendance:excuse:review'),
    ('tasks:create'), ('tasks:assign'), ('tasks:complete'), ('tasks:review'),
    ('announcements:create'), ('announcements:send'),
    ('standing:view_all'),
    ('recruitment:pipeline:view'), ('recruitment:pipeline:update'),
    ('bylaws:query'),
    ('nl_controller:execute')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- member: baseline for every brother. members.role='member' maps here.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'member', x.perm FROM (VALUES
    ('tasks:complete'),
    ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'president', x.perm FROM (VALUES
    ('calendar:event:create'), ('calendar:event:update'), ('calendar:event:delete'),
    ('calendar:officer:view'),
    ('attendance:checkin:create'), ('attendance:override'), ('attendance:excuse:review'),
    ('treasury:budget:view'), ('treasury:audit:view'),
    ('tasks:create'), ('tasks:assign'), ('tasks:complete'), ('tasks:review'),
    ('announcements:create'), ('announcements:send'),
    ('standing:view_all'), ('standing:update'),
    ('recruitment:pipeline:view'), ('recruitment:pipeline:update'),
    ('bylaws:query'), ('bylaws:admin'),
    ('nl_controller:execute'), ('nl_controller:approve')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'vice_president', x.perm FROM (VALUES
    ('calendar:event:create'), ('calendar:event:update'), ('calendar:officer:view'),
    ('attendance:excuse:review'),
    ('tasks:create'), ('tasks:assign'), ('tasks:complete'), ('tasks:review'),
    ('announcements:create'), ('announcements:send'),
    ('standing:view_all'),
    ('bylaws:query'),
    ('nl_controller:execute')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'treasurer', x.perm FROM (VALUES
    ('treasury:invoice:create'), ('treasury:payment:verify'),
    ('treasury:budget:view'), ('treasury:audit:view'),
    ('standing:view_all'),
    ('bylaws:query'), ('tasks:complete')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'secretary', x.perm FROM (VALUES
    ('calendar:event:create'), ('calendar:event:update'), ('calendar:officer:view'),
    ('attendance:checkin:create'), ('attendance:override'), ('attendance:excuse:review'),
    ('announcements:create'), ('announcements:send'),
    ('bylaws:query'), ('tasks:complete')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'risk_chair', x.perm FROM (VALUES
    ('calendar:officer:view'), ('standing:view_all'), ('bylaws:query'), ('tasks:complete')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'social_chair', x.perm FROM (VALUES
    ('calendar:event:create'), ('calendar:event:update'),
    ('tasks:create'), ('tasks:assign'), ('tasks:complete'),
    ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'recruitment_chair', x.perm FROM (VALUES
    ('calendar:event:create'),
    ('recruitment:pipeline:view'), ('recruitment:pipeline:update'),
    ('tasks:create'), ('tasks:complete'), ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'brotherhood_chair', x.perm FROM (VALUES
    ('calendar:event:create'), ('tasks:create'), ('tasks:complete'), ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'philanthropy_chair', x.perm FROM (VALUES
    ('calendar:event:create'), ('tasks:create'), ('tasks:complete'), ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'standards_chair', x.perm FROM (VALUES
    ('standing:view_all'), ('standing:update'),
    ('attendance:excuse:review'), ('bylaws:query'), ('tasks:complete')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'new_member_educator', x.perm FROM (VALUES
    ('calendar:event:create'),
    ('recruitment:pipeline:view'),
    ('tasks:create'), ('tasks:assign'), ('tasks:complete'), ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'alumni_advisor', x.perm FROM (VALUES
    ('calendar:officer:view'), ('bylaws:query')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- ── Legacy backfill ───────────────────────────────────────────────────────────
-- Mirror the legacy members.role into member_roles so the granular path and the
-- legacy path agree from day one. No admin is auto-granted here: production
-- admin bootstrap is a deliberate manual step (scripts/seed.py grants it for the
-- local demo officer).
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT m.chapter_id, m.id, m.role
FROM members m
WHERE m.status = 'active'
  AND m.role IN ('officer', 'member')
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;

-- ── RPCs ──────────────────────────────────────────────────────────────────────
-- Invoked via the service-role client (BYPASSES RLS): tenant guards, idempotency
-- and audit are mandatory, mirroring tr_create_invoice (0080).

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
