-- TREASURY V1 · RBAC seeds (0083 insert style; additive, ON CONFLICT DO NOTHING).
--
-- Decision #2: payment verifiers = full Finance Board (treasurer + finance_board).
-- Decision #5: void/waive = Treasurer ONLY (treasury:invoice:void is NOT granted
-- to finance_board, and never to the generic 'officer' role).

-- ── Role catalog ──────────────────────────────────────────────────────────────
INSERT INTO roles (key, label) VALUES
    ('finance_board', 'Finance Board')
ON CONFLICT (key) DO NOTHING;

-- ── Permission catalog ────────────────────────────────────────────────────────
INSERT INTO permissions (key, description) VALUES
    ('treasury:invoice:void', 'Void / waive invoices (treasurer only; reason required)'),
    ('treasury:fines:issue',  'Issue flat fine invoices for missed required events')
ON CONFLICT (key) DO NOTHING;

-- ── Role→permission matrix ────────────────────────────────────────────────────
-- treasurer: void/waive + fine issuance (+ verify, already seeded in 0083 — kept
-- here so the grant is durable even on a fresh catalog).
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'treasurer', x.perm FROM (VALUES
    ('treasury:invoice:void'),
    ('treasury:fines:issue'),
    ('treasury:payment:verify')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- finance_board: verification queue + fine issuance + treasury read views.
-- Deliberately NOT treasury:invoice:void (decision #5).
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'finance_board', x.perm FROM (VALUES
    ('treasury:payment:verify'),
    ('treasury:fines:issue'),
    ('treasury:budget:view'),
    ('treasury:audit:view'),
    ('bylaws:query'),
    ('tasks:complete')
) AS x(perm)
ON CONFLICT DO NOTHING;

-- admin already holds every permission via 0083's blanket grant for rows that
-- existed then; extend it to the new permission keys.
INSERT INTO role_permissions (role_key, permission_key)
SELECT 'admin', p.key FROM permissions p
WHERE p.key IN ('treasury:invoice:void', 'treasury:fines:issue')
ON CONFLICT DO NOTHING;
