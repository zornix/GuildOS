-- Remove recruitment from the product (2026-10-06 decision).
--
-- The chapter workflow has no recruitment pipeline, candidate status or
-- educator role; those came with the AI-generated prototype. What stays is a
-- "Rush Chair" title whose only grant is creating and updating initiatives.
-- Append-only migration rule: nothing in 0001..0217 is edited.

-- 1. rush_chair replaces recruitment_chair (roles.key is a PK with FKs and no
--    ON UPDATE CASCADE, so: insert the new role, move assignments, drop the old).
INSERT INTO roles (key, label) VALUES ('rush_chair', 'Rush Chair')
ON CONFLICT (key) DO UPDATE SET label = EXCLUDED.label;

INSERT INTO member_roles (chapter_id, member_id, role_key, assigned_by, assigned_at)
SELECT chapter_id, member_id, 'rush_chair', assigned_by, assigned_at
  FROM member_roles
 WHERE role_key = 'recruitment_chair'
ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING;

DELETE FROM roles WHERE key IN ('recruitment_chair', 'new_member_educator');
-- (member_roles and role_permissions rows for both cascade.)

-- 2. rush_chair grants: initiatives only.
INSERT INTO role_permissions (role_key, permission_key)
VALUES ('rush_chair', 'calendar:initiative:create'),
       ('rush_chair', 'calendar:initiative:update')
ON CONFLICT DO NOTHING;

-- 3. Recruitment permissions (cascades to role_permissions for admin/officer/president).
DELETE FROM permissions WHERE key LIKE 'recruitment:%';

-- 4. Recruitment data model.
DROP FUNCTION IF EXISTS rc_update_recruit_stage(UUID, UUID, TEXT, UUID, TEXT);
DROP TABLE IF EXISTS recruits CASCADE;

-- 5. The default "Recruitment" event type, where nothing references it.
DELETE FROM event_types t
 WHERE t.name = 'Recruitment'
   AND NOT EXISTS (SELECT 1 FROM events e WHERE e.event_type_id = t.id);
