-- Announcements SMS permission seed (0083 style).
--
-- SPEC §6: SMS send permission is limited to President and Secretary. The
-- generic 'officer' role (and vice_president, chairs, ...) keep the in-app
-- 'announcements:send' but explicitly do NOT receive 'announcements:send:sms'.
--
-- 0083 grants admin its permissions as per-permission rows materialized at
-- seed time ("SELECT 'admin', p.key FROM permissions p"), so a permission
-- added later needs its own explicit admin row.

INSERT INTO permissions (key, description) VALUES
    ('announcements:send:sms', 'Send announcement SMS blasts (President / Secretary)')
ON CONFLICT (key) DO NOTHING;

INSERT INTO role_permissions (role_key, permission_key)
SELECT x.role, 'announcements:send:sms'
FROM (VALUES ('admin'), ('president'), ('secretary')) AS x(role)
ON CONFLICT DO NOTHING;
