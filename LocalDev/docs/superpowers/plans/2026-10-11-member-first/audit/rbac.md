# RBAC audit: roles, permissions, assignment, consistency

Scope: `LocalDev/` at commit 80e4f8b (2026-10-11). Read-only. Paths are relative to `LocalDev/` unless noted.
Tags: **[FACT]** = read directly in code/migrations (or confirmed with a read-only DB query). **[INF]** = inference or judgement.

Method note [FACT]: I rebuilt the final role→permission matrix by replaying every migration that writes `roles` / `permissions` / `role_permissions` (0083, 0121, 0130, 0144, 0147, 0218). Then I compared it with a read-only `SELECT` against the demo Supabase DB. They match exactly: 36 permission keys, 16 roles, no extra or missing rows. No script or Python code writes the catalog. `scripts/seed.py` and `api/` only read it.

---

## 0. Answers first

- There are **16 roles and 36 permission keys**. The tables are global, not per-chapter, and only role *assignments* are chapter-scoped. There is no role inheritance. Everyone also has an implicit `member` baseline (`tasks:complete` and `bylaws:query`).
- **"Officers hold every permission" (CONTEXT.md) is false for the `officer` role.** It lacks 6 keys: `treasury:invoice:void`, `announcements:send:sms`, `calendar:initiative:create`, `calendar:initiative:update`, `bylaws:admin` and `nl_controller:approve`. Only `admin` holds all 36. Chapter founders get both `officer` and `admin`, so they *do* hold everything [FACT].
- **`president` holds less than `officer`.** It has 22 keys and lacks `roles:assign`, `members:invite`, all treasury write keys and `attendance:checkin_link:manage`, yet it is a protected "top role" [FACT].
- **Two seeded keys are never checked:** `standing:update` and `calendar:initiative:update`. **No key is checked without being seeded** [FACT].
- **Privilege escalation:** any `roles:assign` holder (every `officer`) can grant *themselves* `treasurer`. That gives them `treasury:invoice:void`, which migrations 0121 and 0147 deliberately keep off `officer`. They can also grant themselves `secretary` (SMS). There is no self-assignment guard and no "only grant what you hold" rule. Only `admin` and `president` are ceiling-protected [FACT].
- **Descriptions already exist** in `permissions.description` (0082:20), but **no endpoint returns them**, and roughly half are wrong or incomplete (§5). There is no endpoint that returns role→permission mappings.
- "Officer" has **five different definitions** in the code (§3).

---

## 1. Schema

### Tables [FACT]
| Table | Defined | Scope | Shape |
|---|---|---|---|
| `roles` | migrations/0082_rbac_foundation_tables.sql:12-16 | **global** | `key TEXT PK, label TEXT, created_at`. No description, no chapter_id, no "system" flag |
| `permissions` | 0082:18-22 | **global** | `key TEXT PK, description TEXT NOT NULL DEFAULT '', created_at` |
| `role_permissions` | 0082:24-29 | **global** | PK `(role_key, permission_key)`, both FK `ON DELETE CASCADE` |
| `member_roles` | 0082:36-44 | **chapter-scoped** | `id, chapter_id, member_id, role_key FK→roles ON DELETE CASCADE, assigned_by, assigned_at`, UNIQUE `(member_id, role_key, chapter_id)` |
| `members.role` | legacy, CHECK `officer|member` | per member | display-only since F-022 (0162). `api/rbac/services/permissions.py:21-24` never reads it |

- RLS is enabled on all four tables (0082:72-94), but the app connects as the table owner, so RLS never applies at runtime (CLAUDE.md) [FACT].
- There is **no role inheritance or hierarchy** [FACT]. Effective permissions are `member_roles` keys ∪ `{"member"}` → `role_permissions` (`api/rbac/services/permissions.py:21-49`, `api/rbac/db/repositories/member_roles.py:6-26`). Results are cached per request on `member["_rbac"]` (permissions.py:42-48).
- `admin` is **not implicit**. It holds every key only because each seed migration adds explicit admin rows (0083:59-61, 0121:44-47, 0130:62-65, 0144:672-677, 0147:93-104) [FACT]. A future key added without an admin row would leave admins without it [INF: a drift trap].
- `api/rbac/core/policy.py:19-21` `OWNERSHIP_ESCALATIONS` (`tasks:complete`→`tasks:review`) is **dead in production**: no caller passes `resource=` (grep shows zero hits outside `api/rbac`). `api/tasks/api/tasks.py:94-95` re-implements the rule inline [FACT].

### Migration history of the catalog [FACT]
| Migration | Change |
|---|---|
| 0083 | 15 roles, 26 keys, baseline matrix |
| 0121 | + role `finance_board`; + keys `treasury:invoice:void`, `treasury:fines:issue` |
| 0130 | + key `announcements:send:sms` → admin, president, secretary |
| 0144 (lines 667-677) | + keys `calendar:initiative:create`/`:update` → admin + chair roles |
| 0147 | + role `treasury_viewer`; + 7 keys; widens `officer` and `treasurer` |
| 0162 | backfills `officer` rows; RPC rewrite (legacy column becomes display-only) |
| 0164 | admin tier: auto-admin per chapter, ceiling + last-admin guard |
| 0203 / 0206 | admin-revoke chapter lock / lock ordering |
| 0218 | + `rush_chair` (initiatives only); **deletes** `recruitment_chair`, `new_member_educator`, both `recruitment:*` keys (cascade) |

### FINAL role → permission matrix (after 0218; matches demo DB) [FACT]
Every member also holds the `member` baseline: `tasks:complete` and `bylaws:query`. Counts below are explicit grants only.

| Role (label) | # | Keys |
|---|---|---|
| `admin` (Admin) | 36 | **all** |
| `officer` (Officer) | 30 | announcements:create, announcements:send · attendance:checkin:create, attendance:checkin_link:manage, attendance:excuse:review, attendance:override · bylaws:query · calendar:event:create/update/delete, calendar:officer:view · members:invite · nl_controller:execute · roles:assign · standing:view_all, standing:update, standing:remind · tasks:create/assign/complete/review · treasury:invoice:create, payment:verify, fines:issue, budget:view, audit:view, expense:create, adjustment:create, refund:create, rebuild:run |
| `president` | 22 | announcements:create, send, send:sms · attendance:checkin:create, excuse:review, override · bylaws:query, bylaws:admin · calendar:event:create/update/delete, calendar:officer:view · nl_controller:execute, approve · standing:view_all, standing:update · tasks:create/assign/complete/review · treasury:budget:view, audit:view |
| `vice_president` | 13 | announcements:create, send · attendance:excuse:review · bylaws:query · calendar:event:create/update, calendar:officer:view · nl_controller:execute · standing:view_all · tasks:create/assign/complete/review |
| `treasurer` | 13 | all 10 treasury:* keys · standing:view_all · bylaws:query · tasks:complete |
| `secretary` | 11 | announcements:create, send, send:sms · attendance:checkin:create, excuse:review, override · bylaws:query · calendar:event:create/update, calendar:officer:view · tasks:complete |
| `social_chair` | 8 | calendar:event:create/update · calendar:initiative:create/update · tasks:create/assign/complete · bylaws:query |
| `standards_chair` | 7 | attendance:excuse:review · standing:view_all, standing:update · calendar:initiative:create/update · bylaws:query, tasks:complete |
| `brotherhood_chair` | 6 | calendar:event:create · calendar:initiative:create/update · tasks:create/complete · bylaws:query |
| `philanthropy_chair` | 6 | same as brotherhood_chair |
| `risk_chair` | 6 | calendar:officer:view · standing:view_all · calendar:initiative:create/update · bylaws:query, tasks:complete |
| `finance_board` | 6 | treasury:payment:verify, fines:issue, budget:view, audit:view · bylaws:query, tasks:complete |
| `rush_chair` | 2 | calendar:initiative:create/update |
| `alumni_advisor` | 2 | calendar:officer:view · bylaws:query |
| `treasury_viewer` | 2 | treasury:budget:view, audit:view |
| `member` | 2 | tasks:complete · bylaws:query (implicit for everyone) |

`officer` lacks: `treasury:invoice:void, announcements:send:sms, calendar:initiative:create, calendar:initiative:update, bylaws:admin, nl_controller:approve`.

Stale doc [FACT]: `docs/services/permissions-matrix.md` still lists `recruitment_chair`, `new_member_educator` and `recruitment:*`. It also says permissions are "the union of member_roles and the legacy-compat mapping of members.role" (lines 16-17, 22-34), which has been false since 0162. No test catches this drift.

---

## 2. Permission keys the backend enforces

Gates are `require_permission(...)` (any-of, `api/rbac/auth.py:27-39`), `has_permission(...)` (`api/rbac/services/permissions.py:57-65`), or direct `x in get_member_permissions(...)` checks (events.py:242/281, attendance/api/summary.py:33, calendar/services/calendar.py:137) [FACT].

| Key | Where enforced (route → file:line) |
|---|---|
| **announcements** | |
| announcements:create | POST /api/announcements/ (announcements/api/announcements.py:50); DELETE /api/announcements/{id} (:67); GET /api/announcements/ includes drafts if held (:37) |
| announcements:send | POST /api/announcements/{id}/send (:186); GET /sms-log (:87); GET /outbox (:99); POST /outbox/{row_id}/retry (:114) |
| announcements:send:sms | GET /{id}/sms-preview (:136); POST /{id}/send-sms (:153) |
| **attendance** | |
| attendance:checkin:create | POST /api/attendance/sessions (attendance/api/sessions.py:27) |
| attendance:checkin_link:manage | GET /api/checkin-links/active (attendance/api/checkin_links.py:12); GET/POST/DELETE /api/events/{id}/checkin-link (events/api/events.py:252,258,283); link visible in event lists (events/services/events.py:579) |
| attendance:override | POST /api/attendance/event/{event_id}/manual/{member_id} (attendance/api/attendance.py:111); view anyone's summary (summary.py:24,33) |
| attendance:excuse:review | PUT /api/excuses/{id}/review (excuses.py:104); GET /api/excuses/ returns the whole chapter (:80); view anyone's summary (summary.py) |
| **bylaws** | |
| bylaws:query | GET /api/bylaws/documents (bylaws/api/documents.py:17); POST /api/bylaws/query (:38). The answer is always `not_implemented` (bylaws/services/documents.py:44) |
| bylaws:admin | POST /api/bylaws/documents (:24) |
| **calendar / events / initiatives** | |
| calendar:event:create | POST /api/events/ (events/api/events.py:84) |
| calendar:event:update | PUT /api/events/{id} (:125); manage supervisors on any event (events/services/events.py:807); assign organizers (:893); remove another organizer (:930); send event notifications (events/services/notifications.py:81) |
| calendar:event:delete | DELETE /api/events/{id} (:140) |
| calendar:officer:view | see every event regardless of visibility (events/services/events.py:242,281); GET /api/usage/summary (instrumentation/api/usage.py:32); view anyone's attendance summary (summary.py:24) |
| calendar:initiative:create | POST /api/initiatives/ (initiatives/api/initiatives.py:49) |
| calendar:initiative:update | **never checked**. PATCH /api/initiatives/{id} and chair add/remove use `initiative_chairs` membership only (initiatives/services/initiatives.py:263,319,358) |
| **members / roles** | |
| members:invite | POST /api/auth/invite (auth/api/auth.py:343); POST /api/auth/reset-code/{id} (:479); POST /api/chapters/{id}/roster (chapters/api/chapters.py:64); see every member's SMS consent in GET /api/members/ (members/api/members.py:35) |
| roles:assign | GET/POST /api/rbac/members/{id}/roles, DELETE …/roles/{role_key} (rbac/api/roles.py:52,62,83); PUT /api/members/{id}/role (members/api/members.py:83) |
| **standing / contribution** | |
| standing:view_all | GET /api/standing/ (memberadmin/api/standing.py:12); GET /api/memberadmin/scores (scores.py:17); GET /api/memberadmin/member/{id} (:23); GET /api/contribution/{member_id} (contribution/api/records.py:31) |
| standing:remind | POST /api/memberadmin/remind/{member_id} (scores.py:29) |
| standing:update | **never checked** |
| **tasks (jobs)** | |
| tasks:create | POST /api/tasks/ (tasks/api/tasks.py:33) |
| tasks:assign | commit another member (commitments.py:58); create/manage jobs on any event or initiative (tasks/services/approvals.py:79,86,102) |
| tasks:complete | POST /api/tasks/{id}/report-done (jobs.py:86); POST /api/tasks/{id}/status (tasks.py:94) |
| tasks:review | change status of someone else's job (tasks.py:95); uncommit someone else (commitments.py:85); approve/reject standalone jobs (approvals.py:70); manage standalone jobs (:102) |
| **nl_controller** | |
| nl_controller:execute | GET /api/nl-controller/commands (any-of with approve, commands.py:19); POST /commands (:27). Only queues a row |
| nl_controller:approve | POST /commands/{id}/review (:41). Only flips status; nothing executes (nl_controller/services/commands.py:52) |
| **treasury** | |
| treasury:invoice:create | POST /api/treasury/invoices (invoices.py:82); POST /invoices/bulk, i.e. the dues run (:136); POST /invoices/{id}/cancel (:161) |
| treasury:invoice:void | POST /invoices/{id}/void (:109); POST /api/fines/{id}/waive (fines_legacy.py:222); POST /payments/{id}/reallocate (payments.py:263) |
| treasury:payment:verify | GET /payments/submissions (reports.py:40); verify/reject + v1 variants (payments.py:80,98,193,242); POST /payments/record (:210); view others' evidence and allocations (:185,307); view another member's dashboard (balances.py:59); see all unpaid invoices on the calendar (calendar/services/calendar.py:137) |
| treasury:fines:issue | GET /api/fines/missed/{event_id} (fines_legacy.py:147); POST /api/fines/issue (:175) |
| treasury:budget:view | GET /api/treasury/balance (expenses.py:26); GET /api/treasury/dashboard (reports.py:77) |
| treasury:audit:view | GET /api/treasury/report (reports.py:117); GET /payments/receipts/{id} (payments.py:317); GET /api/fines/summary (fines_legacy.py:243); whole-chapter GET /api/fines/ (:133); any member's balance, statement and dashboard (balances.py:32,59; reports.py:97); calendar invoices (calendar.py:137); treasury rows in the outbox (announcements.py:107,123) |
| treasury:expense:create | POST /expenses, POST /expenses/{id}/invalidate (expenses.py:35,53) |
| treasury:adjustment:create | POST /adjustments, POST /adjustments/{id}/approve (adjustments.py:32,51) |
| treasury:refund:create | POST /api/treasury/refunds (refunds.py:31) |
| treasury:rebuild:run | POST /api/treasury/rebuild (rebuild.py:26) |

**Referenced in code but never seeded:** none [FACT]. All 34 keys used in `api/` exist in the catalog.
**Seeded but never checked:** `standing:update` (officer, president, standards_chair) and `calendar:initiative:update` (admin + 6 chairs) [FACT].

Permission constants are scattered [FACT]. Treasury, members and memberadmin define key constants in route files (`treasury/api/payments.py:23-24`, `members/api/members.py:13,15`, `memberadmin/api/scores.py:10-11`, `memberadmin/api/standing.py:6`, `announcements/api/announcements.py:25`), and some routes use raw string literals (payments.py:185,193,242,263; fines_legacy.py; auth.py; chapters.py; usage.py). That goes against the "auth.py holds domain keys" convention in CLAUDE.md. `treasury`, `members` and `memberadmin` have no `auth.py`.

---

## 3. The "officer" concept

The `officer` role is a **role row with 30 keys**. It is not a flag and it is not "all keys" [FACT]. Code still makes role-name decisions in five places:

| # | Definition | Where | Who counts |
|---|---|---|---|
| 1 | `is_officer()`: holds any role other than `member` | api/rbac/services/permissions.py:18,27-37; used by announcements/services/announcements.py:128-130 (officers-only feed) and announcements/services/sms.py:112-124 (officers SMS audience) | Includes `treasury_viewer`, `alumni_advisor`, `rush_chair`, `finance_board` [FACT] |
| 2 | `OFFICER_ROLES` = 6 chairs + president, VP, treasurer, secretary | api/events/auth.py:16-32; events/services/events.py:823-839 (co-supervisor eligibility, also passed to RPC `ev_add_supervisor` as `p_required_role_keys`) | **Excludes `officer` and `admin`.** A generic officer or admin cannot be a co-supervisor [FACT] |
| 3 | `isOfficerView` = holds `standing:view_all` | greekos/src/lib/session.ts:6,13; App.tsx:83, Sidebar.tsx:77, AppShell.tsx:93 ("Officer"/"Member" badge, dashboard view) | Treasurer counts; social chair and secretary do not [FACT] |
| 4 | `members.role` display column | adapters.ts:70 (shown as "Officer" or "Active Member"), auth/api/auth.py:334, members.py:50 | Only `officer`/`member`. A treasurer-only or admin-only member shows as "Active Member" [FACT] |
| 5 | Hard-coded strings in SQL | rbac RPCs `'admin','president','officer'` (0164:96,113; 0206:31,35,58); `ch_import_roster` (0163); `mem_set_legacy_role` (0154:44-52); `treasury_has_capability` still unions `members.role IN ('officer','member')` (0147:167-171), which is RLS-only and inert at runtime | — |

Other matches from the grep (`.role`, `'officer'`, `is_officer`, `isOfficer`) [FACT]:
- `api/members/api/members.py:110` checks `role not in LEGACY_ROLE_COMPAT` (input validation for the legacy column).
- `CHAIR_ROLES` is imported but unused in events/services/events.py:12; it is only used to build `OFFICER_ROLES`.
- Frontend: `isOfficerView` is exported and used even though the CLAUDE.md conventions table says "Do not: `isOfficer`, `isOfficerView`". The doc and the code contradict each other.
- No backend authorization reads `members.role`. Only display reads remain.

[INF] CONTEXT.md "Officer: holds every permission" should be corrected. In practice "officer" means "admin + officer" for founders, and "officer" (30 keys) for officers who were promoted later.

---

## 4. Role assignment

| Path | Gate | Guards | Audit |
|---|---|---|---|
| POST /api/rbac/members/{id}/roles → `rbac_assign_role` (final body 0164:71-136) | `roles:assign` | Checks the member is in the caller's chapter (0164:92). **Ceiling:** only an admin may grant `admin`/`president` (0164:96-102 → 403 via roles.py:24). Rejects unknown roles. Idempotent (`ON CONFLICT DO NOTHING` + idempotency_keys). Granting `officer` sets `members.role` (0164:113-116) | `ASSIGN_ROLE` row only when a new row is inserted |
| DELETE /api/rbac/members/{id}/roles/{key} → `rbac_revoke_role` (final body **0206**:4-79) | `roles:assign` | Chapter check. **0206 takes `chapters … FOR UPDATE` when revoking `admin`, *before* the ceiling check** (0206:31-33; 0203 had it after). Ceiling for admin/president. **Last-admin:** after the delete, there must be another admin with status active/invited, otherwise `rbac_last_admin` → 409 (0206:47-56). Revoking `officer` resets `members.role` | `REVOKE_ROLE` |
| PUT /api/members/{id}/role?role=officer|member → `mem_set_legacy_role` (0154:20-78) | `roles:assign` | Only `officer`/`member` (members.py:110). Adds or removes only the `officer` member_roles row | ASSIGN_/REVOKE_ROLE with target_table `members` |
| POST /api/chapters/{id}/roster → `ch_import_roster` (0163:3-50) | **`members:invite`** | Refuses `admin`/`president` (0163:19-21; onboarding.py:134). Any other catalog role is assigned | **No audit row and no `assigned_by`** for these role grants [FACT] |
| `ch_create_chapter` (0164:16-69) | PLATFORM_SECRET or rate-limited bootstrap (chapters/auth.py) | Founder gets `officer` + `admin` | none |

Gaps [FACT, severity INF]:
- **No self-assignment guard and no "grant only what you hold" ceiling.** An `officer` (30 keys, no void) can POST `{"role_key":"treasurer"}` for themselves and gain `treasury:invoice:void`. That defeats 0121 "decision #5: void/waive = Treasurer only", which 0147:48-50 and `tests/rbac/test_one_gate.py:149` carefully protect at the *role* level only. Granting `secretary` gives `announcements:send:sms`; granting a chair gives `calendar:initiative:create`. An officer can also revoke `treasurer`, `officer` or anything else from any non-admin. `tests/rbac/test_authority.py:95` ("officer can still grant ordinary roles") makes this behaviour intentional.
- Roster import is a second role-granting path behind a *different* key (`members:invite`) and writes no audit row.
- Unknown role, a member from another chapter or a non-UUID id raise a plain psycopg2 error. `_map_role_error` re-raises it (roles.py:31), so it becomes an opaque **500** (observability.py:96), not a 404/422.
- GET /api/rbac/members/{id}/roles for a member in another chapter returns `[]`, not 404 (roles.py:55) [FACT; harmless].
- The 0206 lock is taken before the ceiling check, so a non-admin attempting an admin revoke briefly locks the chapter row [INF: negligible].
- Idempotency replay ignores the payload (no `request_hash`, unlike tr_* RPCs) [FACT, low].
- The last-admin check counts `invited` admins, who cannot log in until they redeem a setup code. 0164's comment says "who can still log in" [FACT/INF, low].
- The UI (MemberRolesPanel.tsx:31,69-85) shows the full catalog, including `admin`, `president` and `member`, to non-admins. Toggling a top role just returns a 403 [FACT]. Toggling `member` adds a redundant explicit row [INF].

---

## 5. Read endpoints, response shapes, descriptions

- **GET /api/rbac/me/permissions** (roles.py:40-46; schema api/rbac/api/schemas.py:21-23) [FACT] returns:
  `{"permissions": [sorted effective keys incl. member baseline], "roles": [sorted member_roles keys]}`.
  `roles` does **not** include the implicit `member` unless it was explicitly assigned. The UI ignores `roles` (only `perms.permissions` is read, useAppData.ts:108,131).
- **GET /api/rbac/roles** (roles.py:34-37 → member_roles.py:40-41) requires any authenticated member and returns raw `roles` rows: `[{key, label, created_at}]` ordered by key. **It returns no permissions and no description** [FACT].
- **No endpoint lists role→permission mappings. No endpoint lists the permission catalog or descriptions.** Nothing in `api/` reads the `permissions` table (grep for `table("permissions")` finds nothing) [FACT].
- **Descriptions exist** in `permissions.description` (seeded in 0083:28-54, 0121:13-16, 0130:58-60, 0144:667-670, 0147:25-33). Many are wrong when compared with the routes [FACT]:

| Key | Seeded description | What the routes actually do |
|---|---|---|
| roles:assign | "Assign and revoke roles (admin only)" | `officer` holds it; it also covers the officer promote/demote endpoint |
| attendance:checkin:create | "Open check-in sessions / links" | Sessions only; links are `attendance:checkin_link:manage`. No UI call |
| calendar:officer:view | "View officer-visibility events" | Also: see every event, usage analytics, anyone's attendance summary |
| calendar:initiative:create/update | "(chair roles)" | Also `admin`, `rush_chair`; `:update` is never checked |
| standing:update | "Update standing statuses / reason codes" | Never checked |
| standing:view_all | "View all member standings" | Also scores, member detail, anyone's contribution record, and the UI "officer view" |
| tasks:assign | "Assign tasks to members" | Commit others, add or manage jobs on any event or initiative, manage standalone jobs |
| tasks:review | "Review / complete any chapter task" | Approve/reject standalone jobs, uncommit others, change others' job status |
| treasury:invoice:create | "Create invoices" | Also dues runs (bulk) and **cancel** invoice |
| treasury:invoice:void | "(treasurer only; reason required)" | Also admin; also waive fines and **reallocate payments** |
| treasury:payment:verify | "Verify payment submissions" | Also record payments directly, view evidence and allocations, see others' dashboards and calendar invoices |
| treasury:audit:view | "View treasury audit trail" | Any member's balance, statement and dashboard; chapter fines list and summary; report; receipts; outbox treasury rows |
| treasury:budget:view | "View budgets" | Chapter balance + treasury dashboard (there is no "budget" feature) |
| announcements:send | "Send announcements" | Also SMS log, outbox view, outbox retry |
| announcements:send:sms | "(President / Secretary)" | Also admin |
| members:invite | "Invite members and issue password reset codes" | Also roster CSV import (which **assigns roles**) and seeing everyone's SMS consent |
| bylaws:query | "Query bylaws" | Always returns `not_implemented` |
| nl_controller:execute/approve | submit / approve | The queue only; approval executes nothing |

---

## 6. Frontend vs backend consistency

UI keys checked with `can()` [FACT] (App.tsx:49-52,85,126-127,138,164,182-183,221-222,233; config/navigation.ts:30-31; lib/dues.ts:13-21 via FinanceModule.tsx:68-72; lib/session.ts:6):
`attendance:override, calendar:event:create, calendar:event:update, calendar:event:delete, calendar:initiative:create, attendance:checkin_link:manage, attendance:excuse:review, tasks:assign, tasks:create, members:invite, announcements:create, announcements:send, nl_controller:execute, standing:view_all, roles:assign, treasury:invoice:create, treasury:payment:verify, treasury:fines:issue, treasury:adjustment:create`.

- **The UI checks no key that the backend fails to enforce** [FACT]. The test-only literal `events:create` (lib/dues.test.ts:236,256) is not a real key, but it is only used in a test [FACT].
- **Backend keys the UI never checks** (API-only, or no UI surface yet) [FACT]: treasury:invoice:void, budget:view, audit:view, expense:create, refund:create, rebuild:run; announcements:send:sms; attendance:checkin:create; standing:remind; bylaws:query, bylaws:admin; nl_controller:approve; tasks:review; tasks:complete; calendar:officer:view. A legend should label these "not in the app yet" [INF].
- UI gates that disagree with backend per-row authority:
  - Events "Add job" uses only `tasks:assign` (EventsModule.tsx:587,733,743). The backend also allows event supervisors and organizers (approvals.py:73-79) [FACT], so the UI hides an allowed action from them [INF].
  - Initiatives show job controls to chairs by **name string match** `selectedInit.leadChairs.includes(currentMemberName)` (InitiativesModule.tsx:260) [FACT]. This is identity by display name [INF: fragile].
  - **Backend contradiction:** POST /api/tasks/ is gated by `require_permission(tasks:create)` *before* the per-row chair/supervisor checks (tasks.py:30-55). So an initiative chair holding `rush_chair`, `risk_chair` or `standards_chair` (which have no `tasks:create`) **cannot add a job to their own initiative**, although the route comment and approvals.py say chairs may [FACT].
- UI gates that use role names: none use `role_key` names. `isOfficerView` uses a permission key. The roster, filters and dropdowns *display* `members.role` (RosterModule.tsx:42,46,125; FinanceModule.tsx:171,351; EventsModule.tsx:1196; TasksModule.tsx:235; WelcomeBanner.tsx:44) [FACT].
- `refreshOwnPermissions` re-fetches permissions after you edit your own roles (useAppData.ts:101-112) [FACT].

---

## 7. Chapter vs global

- **There is no superadmin or global-admin role** [FACT]. The only global authorities are shared secrets: `PLATFORM_SECRET` (chapter creation, api/chapters/auth.py:49-57) and `CRON_SECRET` (api/cron/auth.py:31-42).
- The catalog (`roles`, `permissions`, `role_permissions`) is **global**. Changing a role's keys changes it for every chapter [FACT].
- Isolation [FACT]: `get_current_user` loads `chapter_id` from the `members` row, not the client (api/dependencies.py:20-27). Permission resolution filters `member_roles` by that `chapter_id` (member_roles.py:6-14). Assign/revoke RPCs check that the target is in `p_chapter_id`, which comes from the session (0164:92, 0206:25). The ceiling check looks for the actor's admin row in the same chapter. Tests: `test_officer_grant_does_not_cross_chapters` (tests/rbac/test_permissions_service.py:63) and `test_assign_rejects_member_outside_chapter` (tests/rbac/test_rbac_rpcs.py:44).
- `member_roles.chapter_id` has no composite FK to `members(id, chapter_id)`. Consistency relies on the RPCs [FACT; low risk, INF].

---

## 8. Custom roles (deferred; assessment only) [INF unless noted]

Could today's schema support admin-created roles and editable permission sets? **Partly. Adding a role row works, but per-chapter editing needs a redesign**, because the tables are global:
1. **Scope:** add `roles.chapter_id NULL` (NULL means a system role) and make uniqueness `(chapter_id, key)`. The key is the PK today, and `member_roles.role_key` / `role_permissions.role_key` are FK'd to it, so either switch to `roles.id UUID` FKs or namespace custom keys (e.g. `c_<chapter>_<slug>`). Otherwise one chapter's edit leaks into every other chapter.
2. **Protected system roles:** add an `is_system` flag. `admin`, `president`, `officer` and `member` are hard-coded in SQL and Python (0164, 0206, 0154, 0163, `is_officer`, `OFFICER_ROLES`) and must not be renamed, deleted or edited. Editing `member` changes everyone's baseline.
3. **Escalation rule:** a new `roles:manage` key, plus a rule that you may only add keys you hold yourself. The same rule should fix the §4 self-grant gap.
4. **Audit:** the `audit_logs.action` CHECK is "frozen" by convention (CLAUDE.md), and there is no action for role-definition edits. Either reuse `ASSIGN_ROLE`/`REVOKE_ROLE` with metadata, or make the case to extend the catalog. Note that `DELETE FROM roles` cascades and silently strips assignments with no audit row (0082:40; 0218 relied on this).
5. **Officer definitions (§3)** would also classify a custom role as "officer" in `is_officer`, which may or may not be wanted.
6. The UI needs a catalog endpoint with descriptions (see §5 and the legend section below).
The resolver (`get_member_permissions`) needs no change: it is a plain union and works with any role rows [FACT].

---

## 9. Tests

`tests/rbac/` [FACT]:
- `test_authority.py`: the legacy column grants nothing; the member baseline; the admin/president ceiling (RPC + HTTP 403); admin hand-off; last-admin 409; inactive admin not counted; the 0206 chapter lock (`:153`).
- `test_rbac_rpcs.py`: multi-role, idempotency, cross-chapter rejection, audit rows.
- `test_one_gate.py`: 17 keys swapped in 0147 resolve via member_roles; `require_officer` and the treasury capability module are gone; void stays off `officer`; the #26 backfill. Its "seeded" check only covers **0147 keys** by grepping the SQL file (`:115-127`).
- `test_legacy_role_sync.py`: PUT /members/{id}/role in both directions, audit, 400/404.
- `test_permissions_service.py`, `test_policy.py`, `test_permission_cache.py`, `test_provision_roles.py`, `test_rush_chair.py` (0218 catalog).

Elsewhere, 403 boundary tests exist in tests/treasury (8 files), announcements (incl. `test_sms_permissions.py`), tasks, events, initiatives, attendance, contribution, chapters, auth and calendar_view. The frontend has `components/*-access.test.ts` (9 files) for UI gates [FACT].

**Missing** [FACT]:
- A test that walks `app.routes` and asserts every `require_permission` key exists in `permissions`, and that every seeded key is used somewhere. This would have caught `standing:update` and `calendar:initiative:update`.
- A self-grant or escalation test.
- An HTTP test for 500 vs 404 on a cross-chapter assign.
- A test that the matrix doc matches the DB.
- No 403 tests for `bylaws:admin`, `nl_controller:*` or `standing:remind` (none found in the grep).

---

## 10. Risks and over-engineering

Risks:
1. **Officer self-grants treasurer → void/waive/reallocate** (§4). High [INF], easy to fix in `rbac_assign_role`.
2. CONTEXT.md "officers hold every permission" is wrong. President < officer. The legend must not repeat the CONTEXT.md claim.
3. Five definitions of "officer" (§3). The audience for officers-only announcements (`is_officer`) differs from co-supervisor eligibility (`OFFICER_ROLES`), from the UI badge (`standing:view_all`) and from the roster label (`members.role`).
4. Two dead keys; the stale matrix doc; misleading seeded descriptions.
5. Roster import grants roles without audit, behind `members:invite`.
6. Chairs without `tasks:create` cannot add jobs to their own initiative (tasks.py:30-33 vs approvals.py:82-86).
7. Unmapped RPC errors on assign/revoke become 500s.

Over-engineering (ponytail) [FACT/INF]:
- `OWNERSHIP_ESCALATIONS` / the `resource=` path in `permission_allows` (policy.py:18-42) has no production caller. Delete it, or use it in tasks.py:94.
- `LEGACY_ROLE_COMPAT` (policy.py:13-16) is now only an input validator for the legacy column (members.py:110). `docs/services/permissions-matrix.md` still describes it as a resolver.
- `CHAIR_ROLES` is imported but unused (events/services/events.py:12).
- The `api/rbac/db/repositories/` directory goes against the CLAUDE.md "no repositories directories" rule.
- `treasury_has_capability` still maps legacy capability strings and `members.role` (0147:129-179). It is RLS-only and inert at runtime.
- Key constants are duplicated across route files (e.g. `treasury:audit:view` is defined three times under different names: RECEIPT_VIEW, RECORD_VIEW, TREASURY_AUDIT_VIEW).

---

## DELIVERABLE: Role legend (derived only from what the routes do)

The baseline every signed-in member has (`member`) is: report your own jobs done and change your own job's status (`tasks:complete`), and read the bylaws list and ask a bylaws question, which returns "not implemented" (`bylaws:query`). It is not repeated below.

| Role | Permission keys (by domain) | What it can actually do (from routes) |
|---|---|---|
| **admin** | all 36 | Everything below, **plus** the only role that can grant or revoke `admin`/`president` (the chapter must keep one admin). Only admin + treasurer can void, waive or reallocate. Only admin + president + secretary can send SMS. |
| **officer** | ann: create, send · att: checkin:create, checkin_link:manage, excuse:review, override · cal: event:create/update/delete, officer:view · members:invite · nl:execute · roles:assign · standing: view_all, update†, remind · tasks: create/assign/review · treasury: invoice:create, payment:verify, fines:issue, budget:view, audit:view, expense:create, adjustment:create, refund:create, rebuild:run | Create, edit and delete any event and see all events; manage door codes and open check-in sessions; mark attendance by hand; review excuses; draft, send and delete announcements and see the outbox; invite members, issue reset codes, import a roster; **assign and revoke non-top roles (including to self)**; see all standings, scores and contribution records and send reminders; create, assign and approve jobs; run dues, create and cancel invoices, verify, reject and record payments, issue fines, record expenses, adjustments and refunds, rebuild the ledger, see all treasury data; submit commands. **Cannot:** void, waive or reallocate, send SMS, create initiatives, add bylaws, approve commands. |
| **president** | ann: create, send, send:sms · att: checkin:create, excuse:review, override · bylaws:admin · cal: event:create/update/delete, officer:view · nl: execute, approve · standing: view_all, update† · tasks: create/assign/review · treasury: budget:view, audit:view | Full events, attendance and announcements control including **SMS blasts**; add bylaws documents; approve or reject commands; see all standings and **read** all treasury data. **Cannot:** assign roles, invite members, door codes, any treasury write, create initiatives. |
| **vice_president** | ann: create, send · att: excuse:review · cal: event:create/update, officer:view · nl: execute · standing: view_all · tasks: create/assign/review | Create and edit events (not delete) and see all events; review excuses; draft and send announcements; see standings and scores; create, assign and approve jobs; submit commands. |
| **treasurer** | treasury: all 10 · standing: view_all | All money operations, **including void, waive and reallocate**; sees all standings and scores. |
| **secretary** | ann: create, send, send:sms · att: checkin:create, excuse:review, override · cal: event:create/update, officer:view | Create and edit events, see all events; open check-in sessions, mark attendance by hand, review excuses; announcements **including SMS**. |
| **social_chair** | cal: event:create/update, initiative:create, initiative:update† · tasks: create/assign | Create and edit any event; create initiatives; create jobs and assign people to jobs. |
| **standards_chair** | att: excuse:review · standing: view_all, update† · cal: initiative:create, initiative:update† | Review excuses; see all standings, scores and contribution records; create initiatives (but cannot add jobs to them: no `tasks:create`). |
| **brotherhood_chair** | cal: event:create, initiative:create, initiative:update† · tasks: create | Create events and initiatives; create jobs. |
| **philanthropy_chair** | same as brotherhood_chair | Same as brotherhood_chair. |
| **risk_chair** | cal: officer:view, initiative:create, initiative:update† · standing: view_all | See all events and usage analytics; see standings and scores; create initiatives (no job creation). |
| **rush_chair** | cal: initiative:create, initiative:update† | Create initiatives only (no job creation, see §6). |
| **finance_board** | treasury: payment:verify, fines:issue, budget:view, audit:view | Review, verify, reject and record payments; issue event fines; read all treasury data. No void, no invoices. |
| **treasury_viewer** | treasury: budget:view, audit:view | Read-only treasury: chapter balance, dashboard, report, any member's balance and statement, all fines. |
| **alumni_advisor** | cal: officer:view | See all events (including officer-only ones), usage analytics, anyone's attendance summary. |
| **member** | tasks:complete, bylaws:query | Baseline (see above). |

† = seeded but **no route checks it**. Leave these out of the legend, or show them as "no effect yet".

### Which keys need a (new or corrected) human description
- **Rewrite** (they are wrong or incomplete today): roles:assign, attendance:checkin:create, calendar:officer:view, calendar:initiative:create, standing:view_all, tasks:assign, tasks:review, treasury:invoice:create, treasury:invoice:void, treasury:payment:verify, treasury:audit:view, treasury:budget:view, announcements:send, announcements:send:sms, members:invite, bylaws:query (mark "not available yet"), nl_controller:execute/approve (queue only).
- **Decide on, then describe or delete:** standing:update, calendar:initiative:update (dead).
- Fine as they are: announcements:create (could add "and delete"), attendance:override, attendance:excuse:review, attendance:checkin_link:manage, calendar:event:create/update/delete, standing:remind, tasks:create, tasks:complete, treasury:fines:issue, treasury:expense:create, treasury:adjustment:create, treasury:refund:create, treasury:rebuild:run, bylaws:admin.
- Roles have no description column at all; only `label` exists.

### Where the description should live so it cannot drift [INF: recommendation]
- **Best: `permissions.description` (already exists).** Correct it in one new migration (`UPDATE permissions SET description = …`), add `roles.description`, and serve both with one endpoint, e.g. extend `GET /api/rbac/roles` to return `[{key, label, description, permissions:[{key, description}]}]` from a `role_permissions` join. The legend then renders exactly what the resolver uses, so the grants cannot drift. Add a route-walk test that asserts every `require_permission` key exists, every seeded key is used, and every description is non-empty. That covers drift in the description text.
- A backend constant dict would duplicate the DB catalog, which is a second source that can drift. A frontend map is worse: it would break the "nothing on screen the server didn't return" rule (CLAUDE.md) and drift silently.
