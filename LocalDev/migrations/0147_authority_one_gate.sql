-- ONE GATE FOR AUTHORITY — permission keys everywhere (imp-one-gate.md Phase A).
--
-- ADR-0001 (permission keys, never role checks) + ADR-0003 (stackable roles, no
-- grant tables). Treasury folds into the central catalog: `treasury_grants` and
-- the `require_capability` dependency are deleted; every treasury gate becomes a
-- `require_permission` catalog key. Seed style follows 0121 (additive,
-- ON CONFLICT DO NOTHING).
--
-- Numbering note: the plan calls this 0146; 0146 was taken by
-- 0146_attendance_tenant_guards.sql, so this lands at 0147.
--
-- CORRECTED IN PLACE 2026-09-03 (issue #26). As written, §5 granted the full
-- `treasurer` role to anyone holding any single legacy write capability, and
-- then dropped `treasury_grants` — destroying the evidence of what each member
-- actually held. Both are fixed below: write-capability holders get
-- `treasury_viewer`, and the table is renamed to `treasury_grants_archived_0147`.
-- The edit is deliberate rather than a follow-up migration, because a follow-up
-- cannot reconstruct a table this file had already dropped. `schema_migrations`
-- stores file names only, so a database that already ran 0147 will not re-run it:
-- any database migrated BEFORE 2026-09-03 received the original behaviour and
-- needs the manual remediation described in issue #26 (only the demo database is
-- known to be in that state; its data is accepted as-is).

-- ── 1. New permission keys ───────────────────────────────────────────────────
INSERT INTO permissions (key, description) VALUES
    ('members:invite',                'Invite members and issue password reset codes'),
    ('attendance:checkin_link:manage','View, generate and kill event check-in links'),
    ('standing:remind',               'Send standing / payment reminders to members'),
    ('treasury:expense:create',       'Record and invalidate chapter expenses'),
    ('treasury:adjustment:create',    'Create and approve finance adjustments'),
    ('treasury:refund:create',        'Issue refunds against verified payments'),
    ('treasury:rebuild:run',          'Run the ledger rebuild / drift report')
ON CONFLICT (key) DO NOTHING;

-- ── 2. New role: view-only treasury access ───────────────────────────────────
INSERT INTO roles (key, label) VALUES
    ('treasury_viewer', 'Treasury Viewer')
ON CONFLICT (key) DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT 'treasury_viewer', x.perm FROM (VALUES
    ('treasury:budget:view'),
    ('treasury:audit:view')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- ── 3. Behavior-preserving grants ────────────────────────────────────────────
-- officer: every key it effectively held through require_officer plus the 0081
-- default treasury grants. Deliberately NOT treasury:invoice:void — 0121
-- decision #5 (void/waive is Treasurer only) stands.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'officer', x.perm FROM (VALUES
    ('members:invite'),
    ('attendance:checkin_link:manage'),
    ('attendance:override'),
    ('attendance:excuse:review'),
    ('tasks:create'),
    ('roles:assign'),
    ('standing:view_all'),
    ('standing:update'),
    ('standing:remind'),
    ('treasury:fines:issue'),
    ('treasury:invoice:create'),
    ('treasury:payment:verify'),
    ('treasury:budget:view'),
    ('treasury:audit:view'),
    ('treasury:expense:create'),
    ('treasury:adjustment:create'),
    ('treasury:refund:create'),
    ('treasury:rebuild:run')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- treasurer: every treasury key, including the four new write capabilities.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'treasurer', x.perm FROM (VALUES
    ('treasury:invoice:create'),
    ('treasury:invoice:void'),
    ('treasury:payment:verify'),
    ('treasury:budget:view'),
    ('treasury:audit:view'),
    ('treasury:fines:issue'),
    ('treasury:expense:create'),
    ('treasury:adjustment:create'),
    ('treasury:refund:create'),
    ('treasury:rebuild:run')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- finance_board: unchanged from 0121 (no new keys, on purpose).

-- admin holds every permission (0083 blanket grant); extend it to the new keys.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'admin', p.key FROM permissions p
WHERE p.key IN (
    'members:invite',
    'attendance:checkin_link:manage',
    'standing:remind',
    'treasury:expense:create',
    'treasury:adjustment:create',
    'treasury:refund:create',
    'treasury:rebuild:run'
)
ON CONFLICT DO NOTHING;

-- ── 4. Backfill member_roles from the legacy members.role column (D6) ────────
-- Audience queries and role listings stop depending on members.role.
-- LEGACY_ROLE_COMPAT stays in the resolver for now (deleting it is a follow-up).
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT chapter_id, id, 'officer'
FROM members
WHERE role = 'officer'
  AND status = 'active'
ON CONFLICT DO NOTHING;

-- ── 5. Migrate then archive treasury_grants ─────────────────────────────────────
-- Prior-migration audit for `treasury_grants` readers:
--   0005 — CREATE TABLE (+ indexes)                       → renamed below
--   0006 — treasury_has_capability() reads it; officer     → function replaced
--          default-grant INSERT; treasury_grants RLS policy   below (policy follows
--                                                              the renamed table)
--   0081 — idempotent officer default-grant INSERT (no trigger, no function)
-- `treasury_has_capability(chapter, capability)` is the ONE live function body
-- that reads the table, and it is still called by RLS policies seeded in 0006,
-- 0010, 0020, 0030, 0040, 0050, 0120, 0123 and 0124. It is re-pointed at the
-- central catalog here, keeping its legacy capability-string argument so none of
-- those policies need to change.

CREATE OR REPLACE FUNCTION treasury_has_capability(p_chapter_id UUID, p_capability TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH me AS (
        SELECT m.id, m.role, m.chapter_id
        FROM members m
        WHERE m.status = 'active'
          AND (
            m.id = treasury_claim_sub_uuid()
            OR m.auth_id = treasury_claim_sub_uuid()
          )
        LIMIT 1
    ),
    wanted AS (
        -- Legacy capability string → catalog permission key(s). ANY-of.
        SELECT unnest(
            CASE p_capability
                WHEN 'treasury:read'     THEN ARRAY['treasury:budget:view', 'treasury:audit:view']
                WHEN 'invoice:create'    THEN ARRAY['treasury:invoice:create']
                WHEN 'payment:review'    THEN ARRAY['treasury:payment:verify']
                WHEN 'expense:create'    THEN ARRAY['treasury:expense:create']
                WHEN 'adjustment:create' THEN ARRAY['treasury:adjustment:create']
                WHEN 'refund:create'     THEN ARRAY['treasury:refund:create']
                WHEN 'rebuild:run'       THEN ARRAY['treasury:rebuild:run']
                ELSE ARRAY[p_capability]
            END
        ) AS permission_key
    ),
    my_roles AS (
        SELECT mr.role_key
        FROM member_roles mr
        JOIN me ON me.id = mr.member_id
        WHERE mr.chapter_id = p_chapter_id
        UNION
        -- LEGACY_ROLE_COMPAT (api/rbac/core/policy.py) mirrored in SQL.
        SELECT me.role
        FROM me
        WHERE me.chapter_id = p_chapter_id
          AND me.role IN ('officer', 'member')
    )
    SELECT EXISTS (
        SELECT 1
        FROM role_permissions rp
        JOIN my_roles r ON r.role_key = rp.role_key
        JOIN wanted w ON w.permission_key = rp.permission_key
    );
$$;

-- Data migration: every treasury_grants holder becomes treasury_viewer.
--
-- Read-only holders keep exactly what they had. Write-capability holders are
-- deliberately UNDER-granted: this catalog has no narrow role that carries a
-- single treasury write key (the roles are officer / treasurer / finance_board /
-- treasury_viewer), and inventing per-capability roles here would smuggle a
-- catalog change into a data migration. The earlier version of this file granted
-- the full `treasurer` role instead, so one legacy `expense:create` row bought
-- treasury:invoice:void — the exact power §3 above keeps off the officer role
-- (0121 decision #5). Under-granting is recoverable; over-granting is not.
--
-- An officer must therefore re-grant treasurer / finance_board deliberately, from
-- treasury_grants_archived_0147 (below), which records what each member held.
INSERT INTO member_roles (chapter_id, member_id, role_key)
SELECT DISTINCT g.chapter_id, g.member_id, 'treasury_viewer'
FROM treasury_grants g
ON CONFLICT DO NOTHING;

-- The 0081-era default grants were a plain idempotent INSERT — there is no
-- trigger or function to drop (verified by grepping every prior migration).
-- The table is renamed rather than dropped so the pre-migration authority set
-- stays auditable (issue #26): it is the only record of who held which write
-- capability, and the grant above deliberately does not reproduce those. Its RLS
-- policy and indexes follow the rename, so the archive stays tenant-guarded.
ALTER TABLE IF EXISTS treasury_grants RENAME TO treasury_grants_archived_0147;
