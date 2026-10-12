# Phase A — Repository audit (member-first GreekOS)

Date: 2026-10-11, main @ 80e4f8b. Read-only; nothing in `api/`, `greekos/` or `migrations/` was changed.
Evidence: nine subsystem reports in `audit/` (each finding tagged FACT or INFERENCE with file:line).
Paths below are relative to `LocalDev/`.

Correction to the brief: the frontend is **Vite + React 19 + Tailwind 4**, not Next.js. There is no router
library, no calendar library, no data-cache library. Backend is FastAPI + raw-SQL migrations (0001–0218).

---

## 1. Executive summary

**The backend is further along than the UI.** Most of what the brief asks for already has an endpoint that the
frontend never calls: the merged calendar range read, the per-event attendance roster, the member statement
(paid invoices + payments), payment reminders, the approval email, SMS announcement blasts, supervisor
management, initiative edit/chairs. The frontend is a 2026-07 prototype that was wired to real endpoints
module by module; Treasury is disciplined, the rest still carries prototype residue (hard-coded dates, fake
default jobs, "GPA 0", "Alpha Chapter", everyone "Good Standing").

**Navigation is a single in-memory string** (`App.tsx:42`). No URL, no back button, no deep links, no reload
persistence. Every mobile/desktop/Officer-Cabin idea in the brief depends on fixing this first.

**Permissions are sound at the route level** (every UI key is enforced server-side, no IDOR found, chapter
scoping correct) but there are real authority gaps: an officer can grant *themselves* `treasurer` (void/waive),
a supervisor can approve their *own* job, a claimant can cancel an event job via the generic status route,
`/set-password` needs no current password, and "officer" has five different definitions in code.

**Communications are system-generated only.** Officers cannot compose an email. Posting an announcement sends
nothing (0188 removed the outbox row). The approval email exists but is thin ("Payment recorded: $X") and can
be lost if the enqueue after commit fails.

**The "natural language controller" is ~200 lines of regex in a React component**; the backend
`nl_controller` package is unconnected scaffolding. No LLM anywhere.

---

## 2. Feature gap matrix

Legend — State: ✅ implemented & accessible · 🔌 backend exists, no UI · 🟡 partial · ❌ missing · ❓ needs decision.
FE = frontend only. BE = backend change (smallest compatible). Risk = L/M/H.

| # | Feature | Existing state | Proposed change | FE only? | Backend changes? | Risk | Relevant files |
|---|---|---|---|---|---|---|---|
| **Navigation & layout** |||||||
| 1 | URL routing / deep links | ❌ `activeTab` state only; back button exits app; `vercel.json:35` has no SPA fallback | Path routing with React Router (D1); lift sub-state (`useEventsChrome`, attendance `selectedEventId`) into the route | FE | `vercel.json` fallback | L | `App.tsx:42`, `hooks/useEventsChrome.ts`, `vercel.json` |
| 2 | Desktop sidebar groups | 🟡 flat 9-item `NAV_ITEMS`, only Outbox/Command gated | Add `group` + per-item permission to `config/navigation.ts`; Home / Chapter / My Activity / Officer Cabin | FE | none | L | `config/navigation.ts`, `Sidebar.tsx`, `layout/AppShell.tsx` |
| 3 | Mobile bottom tabs | ❌ hamburger drawer only; drawer not `inert` when closed; `h-screen` not `dvh` | Bottom tab bar < `lg`; sheets for detail views; safe-area insets; `theme-color` | FE | none | L | `AppShell.tsx`, `Sidebar.tsx`, `ui/Modal.tsx`, `index.html` |
| 4 | Large-screen layout | 🟡 single `max-w-7xl`, no `xl:` anywhere | Fluid container + optional right rail on Home/Events at `xl` | FE | none | L | `AppShell.tsx:98` |
| 5 | Officer Cabin | ❌ officer surfaces live inside shared modules; `isOfficerView` = `standing:view_all` | New group of routes composed from existing officer slices (Outbox, Proof queue, Roll call, Roster admin, Command). Visibility = holds any cabin permission, not a role name | FE | none | L | `App.tsx`, `lib/session.ts:6` |
| 6 | Member Home personalization | 🟡 fixed tiles; "Alpha Chapter" hard-coded; standing faked (member gets 403 on `/api/standing/`); Jobs tile = chapter-wide; 15 requests in 3 waves before first paint | Conditional tiles: my events/required, my jobs, my balance, my excuses; hide empty cards | mostly FE | BE small: a self-readable standing (`/api/standing/me`); per-route loading replaces the 15-call load | L | `DashboardOverview.tsx`, `home/WelcomeBanner.tsx:52`, `useAppData.ts:118-193`, `adapters.ts:78`, `memberadmin/api/standing.py:12` |
| **Login & session** |||||||
| 7 | Show/hide password | ❌ | Toggle on 3 password inputs, `aria-pressed`, keeps `autocomplete` | FE | none | L | `LoginScreen.tsx:125,188,194` |
| 8 | Remember me | ❓ token always in `localStorage`, fixed 7-day JWT, no refresh | Honest minimal: unchecked → `sessionStorage`, checked → `localStorage` (7 d). Longer sessions would need a `remember` flag + TTL settings and a deliberate reversal of the 30→7 day hardening | FE (minimal) | BE only if > 7 days wanted | M | `api.ts:5,54,80`, `auth/api/auth.py:31,61`, `tests/auth/test_tokens.py:87` |
| 9 | Expired/revoked session UX | 🐛 403 "session no longer valid" shows as "Can't reach the chapter server"; `authed` never reset on 401 | Treat auth 403 like 401; reset `authed`; return to login | FE | none | L | `api.ts:169,201`, `useAppData.ts:185-188`, `App.tsx:25` |
| 10 | `/set-password` without current password | 🔒 any token can set a new password | Require current password (except right after redeem) | — | BE small + test | H | `auth/api/auth.py:305-324` |
| **Calendar & events** |||||||
| 11 | Calendar-first page | 🟡 month grid exists and is default; cells unreadable on phones; `GET /api/calendar/` never called; initiatives advertised but not drawn | Month/week grid + agenda list from `/api/calendar/`; phone = agenda feed + compact strip; no library | FE | BE small: include spanning events (`end_date >= start`), add `location`, `event_type_id`, chapter `timezone` | L | `CalendarModule.tsx`, `calendar/services/calendar.py:39,91`, `api.ts` |
| 12 | Event detail view | 🟡 inline right column (1266-line `EventsModule`); no edit UI (`PUT` exists); shows jobs, security, supervisors, organizers (ids only) | Detail sheet/route; wire edit; organizer names | FE | BE optional: `?event_id=` filter on `GET /api/tasks/` (also fixes job visibility leak) | M | `EventsModule.tsx:356-913`, `useEvents.ts:132`, `tasks/services/tasks.py:149` |
| 13 | RSVP | ❌ no concept; closest: `required`, audience, excuses, job claims | Deferred (D6, #118) | — | BE new (if ever) | M | — |
| 14 | Attendance shortcut | 🔌 `GET /api/attendance/event/{id}` roster exists, unused; roll call starts blank every time | "Take attendance" action on event → `/cabin/attendance/:eventId`; preload existing marks | FE | BE small: roster endpoint should respect audience + reject cancelled | L | `AttendanceModule.tsx:56,70`, `attendance/api/attendance.py:49` |
| 15 | Chapter timezone in UI | ❌ not exposed; frontend uses browser clock for 36h lock, "has started" | Expose `chapters.timezone` on `/api/auth/me` | — | BE one field | L | `formatters.ts:17-28`, `auth/api/auth.py:327` |
| **Announcements & comms** |||||||
| 16 | Announcement CRUD | 🟡 create/send/delete exist; create only via Command console; **no update route**; create/delete write no audit row; delete of sent = hide | Form, drafts list, edit, retract | FE + BE | BE small: `PATCH /{id}`, `UPDATE_ANNOUNCEMENT` audit action, audit on create/retract | L | `announcements/api/announcements.py`, `services/announcements.py:263-320` |
| 17 | Communications composer | ❌ officers cannot send email at all; announcement publish sends nothing (0188); SMS blast route exists unused | One composer over the announcement row: destinations = feed / email / calendar slot (SMS deferred, D8) | FE + BE | BE small: `ANNOUNCEMENT_EMAIL` outbox type, `email: bool` on `/send`, enqueue inside the same transaction | M | `0188_announcement_no_outbox.sql`, `platform/outbox.py:117`, `platform/message_templates.py` |
| 18 | Linked calendar event from composer | 🟡 `events.linked_announcement_id` column exists, unused; creating an event already emails every member (`EVENT_CREATED`) | Use the announcement's own calendar slot; do not create real events from the composer | FE | none | M | `0090_events_calendar_links.sql:11`, `events/notifications.py:43` |
| 19 | Email deliverability | 🟡 Gmail/Workspace SMTP app password; plain text; no SPF/DKIM/DMARC anywhere in docs | Human task: domain auth + runbook section | — | docs | M | `docs/ops-runbook.md:232-286`, `platform/email.py` |
| **Roles & permissions** |||||||
| 20 | Role permissions legend | 🔌 `permissions.description` exists (≈18 wrong), never served; no role→keys endpoint; roles have no description | Extend `GET /api/rbac/roles` to return keys + descriptions; correct descriptions by migration; drift test walking `app.routes` | FE + BE | BE small: 1 migration, 1 endpoint extension, 1 test | L | `rbac/api/roles.py:34`, `0082:18-22`, `audit/rbac.md` §5 + legend table |
| 21 | Officer self-grant escalation | 🔒 any `roles:assign` holder (every officer) can grant self `treasurer` → void/waive/reallocate | "Grant only what you hold" in `rbac_assign_role` (D11); audit roster-import role grants | — | BE small + test | H | `0164_rbac_admin_tier.sql:71-136`, `tests/rbac/test_authority.py:95` |
| 22 | Custom roles | ⏸ deferred. Catalog tables are global; keys are PKs | Needs per-chapter scope, system flag, `roles:manage`, audit action — a redesign | — | BE redesign | — | `audit/rbac.md` §8 |
| **Profiles & onboarding** |||||||
| 23 | "Class" field | ❌ no column; UI shows blank `memberClass`; #115 defines it as term joined ("Fall 2024") | `members.member_class TEXT` + validation; self-edit + officer edit (D7) | FE + BE | BE: migration + profile endpoint | L | `adapters.ts:76-83`, issue #115 |
| 24 | My Profile | ❌ no view; **no profile update endpoint at all** (name/phone/email); phone never returned | `/me` returns phone + roles; `PATCH /api/members/me` (name, phone, class); profile page shows standing, roles, SMS | FE + BE | BE small: 1 endpoint, extend `/me` | L | `members/api/members.py`, `auth/api/auth.py:327` |
| 25 | New-member onboarding | ❌ `OnboardingScreen` is pre-login chapter creation; no post-login first-run; reload during "choose password" skips it | Post-login checklist derived from missing fields (no new column); "later" = local snooze; fix redeem-token scope | mostly FE | BE small: redeem token limited to set-password until done | M | `OnboardingScreen.tsx`, `auth/api/auth.py:402-473`, `App.tsx:25` |
| 26 | Email verification | ❌ none; invites/resets already prove inbox on redeem; **chapter signup returns the setup code in the HTTP response** → email squatting + existence oracle | Stop returning the code, email only (D10). Full flow deferred (#119) | — | BE small (now) | M | `chapters/services/onboarding.py:85`, `chapters/api/chapters.py:28-57` |
| **Jobs** |||||||
| 27 | Job permissions (traced) | ✅ create: `tasks:create` (officers + social/brotherhood/philanthropy chairs) — chairs without it can't add jobs to own initiative; claim: any active member incl. creator; report: claimant; approve: event supervisor / initiative chair / `tasks:review` (standalone only) | See §4 | — | — | — | `tasks/api/tasks.py:33`, `tasks/services/approvals.py:60-104` |
| 28 | Self-approval | 🔒 approver is never compared with claimants; supervisor can create→claim→report→approve | Guard: actor must not hold an active commitment; `tasks:review` fallback on event/initiative jobs (D3) | — | BE small + test | M | `approvals.py:60-70`, `0142` `tk_approve_task` |
| 29 | Status-route bypass | 🔒 claimant/assignee can set `cancelled`/`open` on an event job via `/status`, leaving claims active | Remove `/status` once Report-done is in the UI | — | BE small + test | M | `tasks/api/tasks.py:88-97`, `0182` |
| 30 | Job board (active default, priority, history) | 🟡 all statuses in one grid; priority is fake (only `required` exists); no report/approve/reject on Jobs tab; create forces an assignee; due date defaults to 2026-07-16 | Active vs History client-side; sort `required desc, due_at asc`; drop 4-level picker; add Report/Approve/Reject/Unclaim | FE | none | L | `TasksModule.tsx`, `adapters.ts:296`, `useTasks.ts:29` |
| 31 | Standalone jobs skip review | 🐛 Jobs-tab toggle sets `done` → never counts toward contribution | Replace toggle with Report-done | FE (+ #29) | — | L | `useTasks.ts:37-43`, `contribution/services/record.py:126` |
| **Treasury** |||||||
| 32 | Invoice attachments | 🟡 exists: base64 JSON → `payment_evidence` BYTEA, 2 MiB cap, owner-or-verifier reads via API. **No content-type check, no status check, no per-submission cap**; no HEIC handling; no Pillow | Magic-byte sniff PNG/JPEG/HEIC (stdlib), 415 otherwise; pending-only; cap 3 files; client `accept` + size check + re-attach; HEIC → download link | FE + BE | BE small | M | `treasury/api/payments.py:136-167`, `services/payments.py:60-110`, `finance/InvoiceView.tsx:195`, `useFinance.ts:96-107` |
| 33 | Paid invoice history | 🔌 `GET /members/{me}/statement` returns paid invoices + payments; never called. Members' Payments tab is always empty | History tab from `/statement`; fix "My invoices" copy | FE | BE optional: payment `detail` (method, receipt id), rejected submissions + reason | L | `treasury/api/reports.py:84`, `FinanceModule.tsx:270`, `useFinance.ts:153` |
| 34 | Receipt email | 🟡 `PAYMENT_APPROVED` exists, idempotent per submission; body "Payment recorded: $X"; enqueued after commit → can be lost | Term: **receipt**. Enrich payload; retitle "Payment receipt"; enqueue inside the transaction (D15) | — | BE small | L | `treasury/services/payments.py:149-163`, `message_templates.py:79-83` |
| 35 | Unpaid reminders | 🔌 `POST /api/memberadmin/remind/{id}`, 1/member/day dedupe, tested; no UI; no bulk; treasurer lacks `standing:remind`; day computed in server (UTC) time | "Remind" button + bulk with preview; grant key to treasurer; chapter-tz day (D14) | FE | BE small | L | `memberadmin/api/scores.py:27-112`, `treasury/notifications.py:105-138` |
| 36 | Dues run sends no email | 🐛 `bulk_create_invoices` enqueues nothing | Enqueue `INVOICE_ISSUED` per invoice in the run (D15) | — | BE small | L | `treasury/services/invoices.py:238-259` |
| **Officer Cabin / controller** |||||||
| 37 | Natural language controller | 🟡 frontend regex (5 commands); backend `nl_controller` dead; no preview of parsed action; log says "Sent" before server answers; "extend bid" advertised but unparseable; `fine Al $25.50` fines first substring match for $25 | Option A: parser in `lib/command.ts` with tests, verb-anchored, unique-name resolution, cents, parsed-action preview; log attempts to `command_requests` (D12) | FE (+ BE reuse) | none | L | `CommandModule.tsx:52-251`, `nl_controller/`, `audit/nl-controller.md` |

Cross-cutting defects found (not features, but they shape every milestone):

- **Identity by display name** in Events, Attendance, Tasks, Initiatives (`members.find(m => m.name === currentMemberName)`), including the supervisor approve gate. `currentMemberId` is already in `App.tsx:46`.
- **Fabricated values on screen**: "Good Standing" for every member, "$0.00" balances for members, "GPA 0", "Room N/A", "0 hrs", `priority: 'Normal'`, "Alexander Mercer", default jobs that vanish on refetch, 2026-07-16 due dates.
- **Optimistic rows with fake ids** across all mutation hooks, against the "nothing the server did not return" rule.
- **Job card + claim/report/approve UI written three times** (Events, Initiatives, Jobs).
- `GET /api/events/?upcoming` only flips sort; every event ever is returned. `GET /api/tasks/` returns every task including jobs of events the caller can't see.
- Audience is ignored by roster, missed-event list and fines: an officer-only required event can fine members who cannot see it.

---

## 3. Most important architectural and UX issues

1. **No routing.** Blocks bottom tabs, deep links, attendance shortcut, event sheets, Officer Cabin. Fix first.
2. **Startup loads everything** (15 calls, 3 waves, 2–3 guaranteed 403s for members) and has no cache. Home on a phone waits for the slowest officer-only list it never shows.
3. **"Officer" means five different things**: `is_officer` (any non-member role), `OFFICER_ROLES` (chairs + exec, excluding `officer`/`admin`!), `isOfficerView` (`standing:view_all`), `members.role` label, hard-coded SQL strings. CONTEXT.md's "officers hold every permission" is false (`officer` has 30/36; `president` has 22). The Cabin must be permission-driven, not role-driven.
4. **Shared modules branch internally on permissions** rather than composing officer and member views. The Cabin should extract the officer slices rather than duplicate them.
5. **Jobs lifecycle has three holes** (self-approval, status-route bypass, chairs blocked from their own initiative) that must close before "any member creates a job".
6. **Events module is a 1266-line component** with its own confirm dialogs and job cards; the calendar grid is separate and already the default view. The redesign is a recomposition, not a rewrite.
7. **No shared Button/Input/Sheet primitives**; styles drift per file. `animate-in` classes are no-ops (plugin never installed).
8. **Tests**: 151 frontend tests are string-render checks on pure logic and permission gates; nothing covers `App.tsx`, `useAppData`, request/401 handling, or interactions. Backend has ~300 real-DB tests with good RPC coverage but no route-walk test for permission keys.

---

## 4. Biggest reuse opportunities

| Want | Already there (unused by UI) |
|---|---|
| Calendar month/week + agenda | `GET /api/calendar/?start&end` merges events, initiatives, announcements, invoice due, task due |
| Attendance shortcut + prefilled roll call | `GET /api/attendance/event/{id}` (roster + excuse status) |
| Paid invoice history, payment history | `GET /api/treasury/members/{me}/statement` |
| Receipt email | `PAYMENT_APPROVED` outbox event, deduped per submission |
| Unpaid reminders | `POST /api/memberadmin/remind/{id}`, 1/member/day |
| SMS announcement blast with preview | `/{id}/sms-preview` + `/{id}/send-sms` (deferred) |
| Event edit, supervisors add/remove, initiative edit/chairs | routes exist, never wired |
| Role legend text | `permissions.description` column (needs correction) |
| Outbox as "sending history" | `message_outbox` rows per recipient, with status + error |
| Command attempt log / audit | `command_requests` table + `POST /api/nl-controller/commands` |
| Confirm dialog, modal with focus trap | `ui/ConfirmDialog`, `ui/Modal` |
| Pure, tested libs | `lib/dues.ts`, `lib/transaction.ts`, `lib/parseWhen.ts`, `lib/rollCall.ts` |

Proposed job-board workflow verdict (brief §9): steps 2, 3, 6 are frontend-only; step 1 works for current `tasks:create`
holders (opening it to supervisors/chairs on their own parent is a gate move); step 4 needs a Report-done
button plus closing the `/status` hole; step 5 needs the claimant≠approver guard and a `tasks:review` fallback.
Self-claim is fine (capacity + 36h lock + public uncommit log). Self-approval is the real abuse vector; it farms
contribution, not money.

---

## 5. Security and data-integrity concerns, by priority

| P | Issue | Where |
|---|---|---|
| P0 | Officer can grant self `treasurer` (void, waive, reallocate); no "grant only what you hold" | `0164:71-136`, `rbac/api/roles.py:62` |
| P0 | `/set-password` requires no current password; bearer token in `localStorage`; no CSP header | `auth/api/auth.py:305`, `vercel.json:25-30` |
| P0 | Seeded demo admin password is committed (`scripts/seed.py:34`) and prod `DATABASE_URL` still points at the demo DB | `CLAUDE.md` |
| P0 | Evidence upload: any `content_type` stored, uploads allowed after approval, unbounded count | `treasury/services/payments.py:60-110` |
| P1 | Job self-approval; claimant can cancel/reopen an event job via `/status` | `approvals.py:60`, `tasks.py:88-97` |
| P1 | Approval/receipt email enqueued after commit → silently lost on enqueue failure, never retried | `treasury/services/payments.py:149-163` |
| P1 | Unauthenticated chapter signup returns the setup code → email/chapter-name squatting + email existence oracle | `chapters/services/onboarding.py:85` |
| P1 | Audience ignored by roster/fines → members who cannot see a required event can be fined | `attendance/api/attendance.py:65`, `signals.py:77` |
| P1 | Fabricated standing/balances on member screens (403 swallowed into defaults) | `adapters.ts:69,78`, `useAppData.ts:128` |
| P1 | Revoked session (403) presented as server outage | `api.ts:169,201` |
| P2 | Credential changes (set/reset/redeem) write no audit row; roster import grants roles without audit | `0191`, `0163` |
| P2 | Login lockout is pre-password (10 bad tries lock the real user out); `login_attempts` never pruned; bcrypt >72 bytes → 500 | `auth/api/auth.py:180-201` |
| P2 | Event `PUT`, hard delete, excuse submit, check-in link create/kill write no audit row | `events/services/events.py:716`, `excuses.py:17` |
| P2 | Vercel Hobby plan allows only daily crons; outbox drain is `*/5` | `vercel.json` |

---

## 6. Order for Phase B discussions (as held on 2026-10-11)

1. Foundation: routing, nav groups, mobile tabs, Officer Cabin visibility rule.
2. "Me" data: Home, My Profile, class, onboarding, session fixes.
3. Calendar & events, attendance shortcut, RSVP decision.
4. Jobs guards, then the board.
5. Treasury member views.
6. Announcements & composer.
7. Roles legend (+ self-grant fix).
8. Cabin content & controller.

---

## 7. NL controller: option summary (brief §11)

| | A: deterministic | B: hybrid Haiku fallback | C: bounded agent |
|---|---|---|---|
| Work | 150–250 LOC + tests, 1–2 days | +250–400 LOC, API key, eval set, 3–5 days | 1–3k LOC, weeks |
| Latency | <1 ms | +0.5–2 s on fallback | seconds, multi-call |
| $/command | 0 | ≈$0.0002–0.0003 (Haiku 5.5) | $0.002–0.30 |
| $/month at 1 / 5 / 20 chapters | 0 | $0.06–0.23 / $0.30–1.10 / $1.20–4.50 (worst case, every command) | $5–150+ |
| Security | none new | member data to third party; validator must enforce intent enum, cents cap, name→one member, verbatim text, human confirm | partial-failure/compensation problem |
| Recommendation | **Now** (D12) | only if logged attempts show >10–15% paraphrase failures over ~4 weeks | only for multi-step workflows |

The Officer Cabin is useful without any of this; the console is one tile inside it.
