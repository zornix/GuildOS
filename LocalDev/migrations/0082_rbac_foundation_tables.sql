-- RBAC foundation: role catalog, permission catalog, role→permission matrix,
-- and member role assignments. Additive on top of the legacy members.role column
-- (which keeps its CHECK (role IN ('officer','member')) and keeps working).
--
-- Roles are NOT time-bounded: a member holds a role until it is revoked.
-- Role assignment is admin-gated (the 'roles:assign' permission).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Catalogs (global, not chapter-scoped) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS roles (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permissions (
    key TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_key TEXT NOT NULL REFERENCES roles(key) ON DELETE CASCADE,
    permission_key TEXT NOT NULL REFERENCES permissions(key) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_key, permission_key)
);

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_key
    ON role_permissions(permission_key);

-- ── Member role assignments (chapter-scoped; a member may hold many roles) ───

CREATE TABLE IF NOT EXISTS member_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    role_key TEXT NOT NULL REFERENCES roles(key) ON DELETE CASCADE,
    assigned_by UUID REFERENCES members(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_member_roles_member_role_chapter UNIQUE (member_id, role_key, chapter_id)
);

CREATE INDEX IF NOT EXISTS ix_member_roles_chapter_id ON member_roles(chapter_id);
CREATE INDEX IF NOT EXISTS ix_member_roles_member_id ON member_roles(member_id);
CREATE INDEX IF NOT EXISTS ix_member_roles_role_key ON member_roles(role_key);

-- ── RLS ───────────────────────────────────────────────────────────────────────

-- Requester's chapter, resolved from the JWT sub via the shared treasury helper
-- (defined in 0006; generic despite the name). SECURITY DEFINER so the policy
-- can read members regardless of the caller's row access.
CREATE OR REPLACE FUNCTION rbac_request_chapter_id()
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT m.chapter_id
    FROM members m
    WHERE m.status = 'active'
      AND (
        m.id = treasury_claim_sub_uuid()
        OR m.auth_id = treasury_claim_sub_uuid()
      )
    LIMIT 1
$$;

ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_roles ENABLE ROW LEVEL SECURITY;

-- Catalogs are non-sensitive reference data: readable by any authenticated member.
DROP POLICY IF EXISTS roles_select_all ON roles;
CREATE POLICY roles_select_all ON roles
    FOR SELECT USING (true);

DROP POLICY IF EXISTS permissions_select_all ON permissions;
CREATE POLICY permissions_select_all ON permissions
    FOR SELECT USING (true);

DROP POLICY IF EXISTS role_permissions_select_all ON role_permissions;
CREATE POLICY role_permissions_select_all ON role_permissions
    FOR SELECT USING (true);

-- Assignments are chapter-scoped reads.
DROP POLICY IF EXISTS member_roles_select_chapter ON member_roles;
CREATE POLICY member_roles_select_chapter ON member_roles
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- Writes go exclusively through the rbac_* RPCs (service-role client, which
-- bypasses RLS); no INSERT/UPDATE/DELETE policies are defined on purpose.

-- ── audit_logs action catalog extension (additive) ───────────────────────────
-- audit_logs is shared infrastructure (0005). New domains write their actions
-- here too, so the CHECK constraint grows additively. Existing values unchanged.
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check;
ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (
    action IN (
        -- treasury (0005)
        'CREATE_INVOICE',
        'VERIFY_PAYMENT',
        'REJECT_PAYMENT',
        'CREATE_EXPENSE',
        'INVALIDATE_EXPENSE',
        'CREATE_ADJUSTMENT',
        'CANCEL_INVOICE',
        'ISSUE_REFUND',
        'REBUILD',
        -- rbac
        'ASSIGN_ROLE',
        'REVOKE_ROLE',
        -- tasks
        'CREATE_TASK',
        'UPDATE_TASK_STATUS',
        -- announcements
        'CREATE_ANNOUNCEMENT',
        'SEND_ANNOUNCEMENT',
        -- recruitment
        'CREATE_RECRUIT',
        'UPDATE_RECRUIT_STAGE',
        -- nl controller
        'CREATE_COMMAND_REQUEST',
        'REVIEW_COMMAND_REQUEST'
    )
);
