# Implementation plan — one gate for authority (permission keys everywhere)

Date: 2026-07-11
Order: step 4 of 7. Depends on: `imp-platform-module.md`.
Scope: backend + frontend. This is the review's top recommendation
(candidate 1). Supersedes `imp-fe-remediation.md` Phase C (its D3 decision —
keys are backend-owned, seeded gaps go in a migration — carries over verbatim).

Contract: decisions settled here; implementer executes as written, reports
drift. Authority: ADR-0001 (permission keys, never role checks), ADR-0003
(stackable roles, no grant tables), `CONTEXT.md` (Permission / Role /
Standing).

## Settled decisions

- **D1 — Treasury folds into the central catalog** (ADR-0003, decided
  2026-07-11). `require_capability` + `treasury_grants` are deleted; the 21
  treasury call sites gate on `require_permission` with catalog keys. The
  `treasurer` and `finance_board` roles already exist (0121); a
  `treasury_viewer` role is added for view-only access.
- **D2 — Everyone uses a password** (product decision, 2026-07-11). The
  officer-only password rule is deleted, not generalized: *any* member with a
  `password_hash` must supply the password to log in; *any* member without
  one gets `password_setup_required: true` on first login and may call
  `set-password` on their own account. No role check anywhere in the auth
  flow. (Known pre-existing exposure, unchanged by this plan: an account that
  has never logged in can be claimed by whoever knows the email first —
  flag as a follow-up for the invite flow, do not fix here.)
- **D3 — `require_officer` and the frontend `OFFICER_ONLY` array are
  deleted.** Every gate goes through `Depends(require_permission(...))` on
  the backend and `usePermissions().can(key)` on the frontend.
- **D4 — Rendering a subject's role as a badge/label is data display, not a
  gate** (ADR-0001 carve-out). `page-header.tsx:17` and the members-list role
  badge stay. The members-view *role toggle control* is a gate → `roles:assign`.
- **D5 — Data-scoping follows the same keys.** "Officer sees all, member sees
  own" branches resolve via `permissions.has_permission(user, <key>)` with
  the same key that gates the corresponding review/audit surface.
- **D6 — `member_roles` gets backfilled from `members.role`** so audience
  queries and future role listings don't depend on the legacy column.
  `LEGACY_ROLE_COMPAT` stays for now (deleting it is a follow-up once the
  roles UI is the only assignment path).

## Phase A — migration `0146_authority_one_gate.sql`

Follow the 0121 seed style (additive, `ON CONFLICT DO NOTHING`).

1. New permission keys: `members:invite`, `attendance:checkin_link:manage`,
   `standing:remind`, `treasury:expense:create`,
   `treasury:adjustment:create`, `treasury:refund:create`,
   `treasury:rebuild:run`.
2. New role: `treasury_viewer` ('Treasury Viewer') →
   `treasury:budget:view`, `treasury:audit:view`.
3. Grants preserving today's behavior: `officer` role gets every key it
   effectively held via `require_officer` + the 0081 default treasury grants
   (all of step 1's keys plus existing `attendance:override`,
   `attendance:excuse:review`, `tasks:create`, `roles:assign`,
   `standing:view_all`, `standing:update`, `treasury:fines:issue`,
   `treasury:invoice:create`, `treasury:payment:verify`,
   `treasury:budget:view`, `treasury:audit:view`) — but **not**
   `treasury:invoice:void` (0121 decision #5 stands). `treasurer` gets all
   treasury keys incl. the four new ones; `finance_board` adds none beyond
   0121. `admin` extends to all new keys (0121 pattern).
4. Backfill (D6): `INSERT INTO member_roles (chapter_id, member_id, role_key)
   SELECT chapter_id, id, 'officer' FROM members WHERE role = 'officer' AND
   status = 'active' ON CONFLICT DO NOTHING`.
5. Migrate then drop `treasury_grants`: **first grep all prior migrations for
   `treasury_grants`** — if any live plpgsql RPC body reads it, update that
   function in this migration before the drop. Data migration: members whose
   grant rows are read-only (`treasury:read` only) → assign `treasury_viewer`;
   members with any write capability who don't already resolve to equivalent
   keys through a role → assign `treasurer`; officers need nothing (step 3
   covers them). Then `DROP TABLE treasury_grants` (it is not append-only; no
   ledger concern). Also delete the 0081-era default-grant trigger/function if
   one exists.

## Phase B — backend route swap

6. Replace all 21 `require_capability` sites (6 treasury files) per this map,
   then delete `require_capability` and everything else in
   `api/treasury/auth.py` (file goes away; constants move to the route files
   or a keys module):
   `treasury:read` → `treasury:budget:view` (balances/reports) or
   `treasury:audit:view` (ledger/audit endpoints — judge per endpoint,
   report the final mapping); `invoice:create` → `treasury:invoice:create`;
   `payment:review` → `treasury:payment:verify`; `expense:create` →
   `treasury:expense:create`; `adjustment:create` →
   `treasury:adjustment:create`; `refund:create` → `treasury:refund:create`;
   `rebuild:run` → `treasury:rebuild:run`.
7. Replace the 14 `require_officer` sites, then delete `require_officer`
   from `api/dependencies.py`:
   - `auth/api/auth.py:124` invite → `members:invite`
   - `attendance/api/attendance.py:166` manual check-in → `attendance:override`
   - `attendance/api/excuses.py:93` review → `attendance:excuse:review`
   - `attendance/api/checkin_links.py:10` + `events/api/events.py:262,285`
     (link view/generate/kill) → `attendance:checkin_link:manage`
   - `tasks/api/operations.py:19` apply template → `tasks:create`
   - `members/api/members.py:25` update role → `roles:assign`
   - `treasury/api/fines_legacy.py:249` process fines → `treasury:fines:issue`
   - `treasury/api/fines_legacy.py:270` fine summary → `treasury:audit:view`
   - `memberadmin/api/scores.py:12,18` → `standing:view_all`; `:24` reminder
     → `standing:remind`
   - `memberadmin/api/standing.py:10` → `standing:view_all`
8. Data-scoping (D5): `attendance/api/excuses.py:72` sees-all iff
   `attendance:excuse:review`; `treasury/api/fines_legacy.py:131` sees-all
   iff `treasury:audit:view`.
9. `announcements/services/sms.py:116`: officer audience = members holding
   the `officer` role in `member_roles` (post-backfill), dropping both the
   `m["role"] == "officer"` compare and the ad-hoc `rbac_officers` union.

## Phase C — everyone uses a password (D2)

10. `api/auth/api/auth.py`: at `:47` drop `member["role"] == "officer" and` —
    password is required whenever `password_hash` is set; at `:62` drop the
    role check — `password_setup_required` for any member without a hash; at
    `:96` drop the officer check on `set-password` (any authenticated member,
    own account — it already writes only `user["id"]`).
11. Frontend: verify the login form already handles `PASSWORD_REQUIRED` and
    `password_setup_required` for non-officers (it was officer-only UX);
    adjust copy/flow so a regular member is walked through setting a
    password. Update auth e2e fixtures — member personas now have passwords.
12. Tests: update `tests/` auth cases; add one pinning "member without hash →
    setup required; member with hash → password enforced".

## Phase D — frontend gates

13. `config/navigation.ts`: delete `OFFICER_ONLY` (line 40); nav entries get
    `requiredPermission`: standing → `standing:view_all`, active-checkins →
    `attendance:checkin_link:manage`.
14. `components/layout/app-shell.tsx:21,44` and `sidebar.tsx:6,48`: drop the
    legacy gate; `can(requiredPermission)` is the only filter.
15. View swaps (map each compare to the key of the action it reveals):
    `views/standing.tsx:25,29` → `standing:view_all` ·
    `views/events.tsx:48,101,171,209` → `attendance:checkin_link:manage` /
    `attendance:override` / `treasury:fines:issue` / `calendar:event:delete`
    per site · `views/dashboard.tsx:22,41,46,71` → key of each widget
    (pending excuses → `attendance:excuse:review`, unpaid-total →
    `treasury:audit:view`, …) · `views/fines.tsx:51,64` →
    `treasury:audit:view` · `views/members.tsx:21,49,50,52` → gate =
    `roles:assign`, badge = display (D4). `page-header.tsx:17` stays (D4).
16. Rewrite `config/navigation.test.ts:34` to pin the *new* invariant: nav
    filtering is purely permission-key-driven (a persona with
    `standing:view_all` sees standing regardless of any role string).
17. Acceptance grep (fe-remediation D3 contract): `role ===` / `role !==` in
    `fratos/views/` and `fratos/components/` returns only D4 display sites;
    `require_officer` and `OFFICER_ONLY` return zero repo-wide.

## Verification

`python3 -m pytest` (treasury suite exercises the folded gates; expect
fixture updates from `treasury_grants` → roles). `npm run migrate` clean on
demo. From `fratos/`: lint, unit, build, and `npm run test:e2e` (the role
flows are the point of this plan — auth, events, fines, excuses, checkin,
members must all pass with key-gated personas).

Suggested commits: one per phase
(`feat(rbac): ...` / `feat(auth): everyone uses a password` / `refactor(fratos): permission-key gates`).
