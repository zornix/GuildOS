# GreekOS forensic audit — 2026-09-30

> **How to read this.** Page one (TL;DR + Top 10) is enough to make decisions. Every later section opens with **In short**. Click a ▸ to expand detail. IDs like F-022 link to a finding card in §3. Severity tags: 🔴 P0 · 🟠 P1 · 🟡 P2 · 🔵 P3 · ⚪ P4.

## TL;DR

- **The database functions are good. The Python and React around them are not.** Money, roles, attendance overrides and job claims are atomic and audited inside plpgsql. Almost everything else is a chain of autocommitted statements that can stop halfway.
- **Authority has two sources of truth and they disagree.** A legacy `members.role` column is unioned into permissions, so revoking an officer through the RBAC API does nothing, a roster CSV grants officer to any non-member role, and any officer can grant themselves admin.
- **Standing and balances are computed from the wrong numbers.** A one-cent payment clears a fine for standing; today's events count as missed before they start; dashboards read a cache that excuse approval never refreshes.
- **The finance tab lies.** "Add transaction" toasts success and saves nothing. Officers and members see a screen that does not match the server.
- **This is agent-built and it shows**: parallel implementations, docs that describe a tree that does not exist, test-era abstractions shipped as architecture, and a hand-copied production folder nobody can reproduce.
- **Tests are real but blind in two places**: every test connects as the table owner (RLS never runs), and the RBAC and balance tests mock the thing under test.
- **No P0.** 68 findings kept: 27 P1, 27 P2, 14 P3. Three findings were refuted and dropped. Every P1 was cross-checked by a second vendor and eye-checked by the lead.

| **Trust** | **Distrust** | **Change before building on it** |
|---|---|---|
| Treasury RPCs (`tr_*`), the outbox claim protocol, `Money`, JWT/setup-code handling, job and swap state machines, the pure frontend adapters | `members.role` and anything that reads it; standing numbers; `member_finance_accounts` readers; the Finance tab's write actions; any Python function that does more than one write; `Prod/` as a description of production; `CLAUDE.md`'s frontend section | Collapse authority to one source; make standing and balance read live data; move multi-step writes into RPCs; wire or remove fake UI actions; make `Prod/` a build output of `LocalDev/`; write the ten Phase-0 tests |

## Top 10 (highest engineering impact first)

| # | ID | Sev | One line | Fix size |
|---|---|---|---|---|
| 1 | [F-022](#f-022) | 🟠 | Revoking the officer role through the RBAC API does not revoke officer permissions (legacy column wins) | small |
| 2 | [F-023](#f-023) | 🟠 | `roles:assign` has no ceiling: any officer can make themselves admin, president or treasurer | small |
| 3 | [F-014](#f-014) | 🟠 | Finance "Add transaction" (payment, invoice, fine, adjustment) never reaches the server | small |
| 4 | [F-027](#f-027) | 🟠 | Officers can credit their own account below the $500 sign-off, and can verify their own payment | small |
| 5 | [F-024](#f-024) | 🟠 | A one-cent partial payment makes a fine vanish from standing; F-015 and F-002 are the same query | small |
| 6 | [F-028](#f-028) | 🟠 | Treasurer dashboard, CSV and reminder SMS read a balance cache that excuse approval never refreshes | small |
| 7 | [F-011](#f-011) | 🟠 | Every Python multi-step write autocommits; event update, task create, onboarding and check-in can half-apply | architectural |
| 8 | [F-019](#f-019) | 🟠 | Outbox marks "sent" after the provider call in a separate commit; inline SMS also races the cron drain (F-017) | medium |
| 9 | [F-010](#f-010) | 🟠 | Production code and schema cannot be reproduced from the repo | medium |
| 10 | [F-037](#f-037) | 🟠 | Setup and reset codes sit in plaintext in failed outbox rows for their 7-day life | medium |

## 1 · Executive summary

**In short:** GreekOS is a coherent design implemented unevenly. The treasury core would pass a serious review. The layers that were added faster, by more agents, would not. The risk is concentrated in four places: role authority, standing and balance readers, non-atomic Python writes, and a frontend that reports success it did not earn.

<details><summary>▸ The nine questions the brief asks</summary>

| Question | Answer |
|---|---|
| Is the architecture coherent? | At the database and RPC level, yes: one write pattern (guard, idempotency key, audit, ledger). Above it, no: three task surfaces over one table, two fine pipelines, two payment-verify functions, a template engine nobody calls, and a frontend with no routing and 1,200-line modules. |
| Maintainable? | The backend is, once the parallel paths are deleted. The frontend needs its modules split and its state model replaced before it is safe to extend. |
| Signs of fragmented agent development? | Strong. Seven helpers exist in two or more copies, plan identifiers live in comments, docs describe directories that do not exist, and test scaffolding is presented as architecture (§8). |
| Correctness guarantees strong or implicit? | Strong for money movement and job claims (database enforced). Implicit for attendance, fines, excuses, standing and roles: those rules live in one Python handler or in a comment (Appendix A). |
| Security boundaries centralized or scattered? | One permission resolver and one JWT verifier, which is good. But the resolver unions a legacy column that revoke never clears, ownership checks compare a string to a UUID, and the production guard only arms on Vercel. Centralized, with holes in the center. |
| Are database constraints doing enough? | For money, yes. For attendance, fines, roles and migrations, no: no unique fine per event+member, no "excused xor fined", no column/table agreement for roles, no migration checksum. RLS exists on 43 tables and is never exercised. |
| Does the test suite protect? | Yes for treasury RPCs, auth, outbox and chapter onboarding. No for tenant isolation (superuser connection), RBAC resolution (`FakeSb`), and balance derivation through HTTP (mocked). |
| Strongest parts | `tr_*` RPCs with allocations; outbox claim protocol; `Money`; auth basics; tasks and security-swap state machines; pure adapters and `lib/*.ts`. |
| Largest engineering risk | The authority model (F-022, F-023, F-006), then the readers of standing and balance (F-024, F-028, F-015, F-002, F-004), then the autocommit pattern (F-011) that makes every fix above fragile until it is closed. |
</details>

<details><summary>▸ How the numbers break down</summary>

| | P1 | P2 | P3 | Total |
|---|---|---|---|---|
| Security / authority | 8 | 4 | 3 | 15 |
| Financial / standing | 9 | 6 | 2 | 17 |
| Correctness (workflows, notifications) | 8 | 8 | 1 | 17 |
| Ops / config / deploy | 2 | 5 | 1 | 8 |
| Maintainability / tests / frontend | 0 | 4 | 7 | 11 |

Confidence: 63 confirmed, 4 likely, 1 speculative (F-008, which depends on a Supabase setting outside the repo).
</details>
## 2 · Architecture map

**In short:** one FastAPI app, one React single-page app, one Postgres database on Supabase. Twenty-two routers, 140 route handlers, 55 tables, 77 database functions. The database functions are where the real rules live.

| Layer | Where | Size | What it really is |
|---|---|---|---|
| Backend | `LocalDev/api/` | 15.3k lines Python, 140 handlers | One FastAPI app (`api/index.py`) mounting 22 routers, one package per domain |
| Database | `LocalDev/migrations/` | 65 SQL files, 55 tables, 77 plpgsql functions, 26 triggers | Raw SQL migrations applied in filename order. Money and role changes go through functions prefixed `tr_`, `rbac_`, `at_`, `ev_`, `tk_` |
| Frontend | `LocalDev/greekos/src/` | 12.6k lines TypeScript, 87 files | Vite + React 19. No router: `App.tsx` switches on a tab. One 722-line `api.ts` holds the fetch client and every DTO |
| Tests | `LocalDev/tests/`, `greekos/src/**/*.test.ts` | 87 + 22 files, 1030 + 86 runs | Backend tests hit the real Supabase demo database as superuser |
| Deploy | `Prod/` | hand-copied snapshot | Vercel serves `Prod/api` (Python function) and `Prod/fratos` (static build). Not generated from `LocalDev` |
| Cron | `vercel.json` | 1 job | `GET /api/cron/drain-outbox` every 5 min sends queued email and SMS |

<details><summary>▸ Backend domains (routes · tables they own · notes)</summary>

| Domain | Mount | Handlers | Owns | Notes |
|---|---|---|---|---|
| auth | `/api/auth` | 7 | member auth columns, `member_setup_codes`, `login_attempts` | HS256 JWT, 7-day expiry, `ver` claim vs `members.token_version` |
| rbac | `/api/rbac` | 6 | `roles`, `permissions`, `role_permissions`, `member_roles` | One permission resolver; legacy `members.role` still unioned in |
| members, chapters | `/api/members`, `/api/chapters` | 5 | `members`, `chapters` | Unauthenticated chapter self-signup; CSV roster import |
| events | `/api/events` | 23 | `events`, types, groups, organizers, supervisors, audience, notification sends, `security_swap_requests` | 754-line service; security shifts and swaps live here |
| attendance | `/api/attendance`, `/api/excuses`, `/api/checkin-links`, `/c` | 12 | `attendance`, `excuses`, `checkin_links`, `attendance_sessions` | Public HTML check-in page, phone check-in, manual roll call |
| treasury | `/api/treasury`, `/api/fines` | 34 | invoices, submissions, evidence, verified payments, allocations, receipts, refunds, adjustments, expenses, `member_finance_accounts`, `big_ledger`, `audit_logs`, `idempotency_keys`, frozen `fines` | The reference domain. Money moves only through `tr_*` functions |
| tasks | `/api/tasks`, `/api/operations` | 17 | `tasks`, groups, commitments, commitment log, legacy `event_templates*` | Three surfaces (tasks, jobs, commitments) over one table, plus an orphaned template engine |
| initiatives | `/api/initiatives` | 6 | `initiatives`, `initiative_chairs` | |
| announcements | `/api/announcements`, `/api/twilio` | 10 | `announcements`, `announcement_sms_sends`, `message_outbox` view | SMS blast, outbox retry, Twilio inbound STOP/START |
| cron | `/api/cron` | 2 | `message_outbox` drain | `process-fines` is a disabled no-op |
| memberadmin, contribution, calendar, recruitment, instrumentation | various | 12 | derived views, `recruits`, `usage_events` | Standing and engagement scores are computed, never stored |
| bylaws, nl_controller | `/api/bylaws`, `/api/nl-controller` | 6 | stubs | Return explicit `not_implemented` |

Platform layer `api/platform/`: `postgres.py` is a PostgREST-shaped query builder over psycopg2 with a per-process pool. **Every statement autocommits.** Only plpgsql functions are atomic. The app connects as the table owner, so row-level security never applies.

Request path: handler → `get_current_user` → `require_permission` (2 queries) → service → either autocommitted statements or one RPC → response.
</details>

<details><summary>▸ Database layers and what is enforced there</summary>

| Migration range | What it added |
|---|---|
| 0001–0004 | MVP tables: chapters, members, events, attendance, excuses, fines |
| 0003 | "Operations engine": templates, roles, post-event reports. Unreachable from the UI today |
| 0005–0080 | Treasury: ledger, invoices, payments, allocations, refunds, adjustments, tenant guards |
| 0082–0089 | RBAC catalog and RPCs; announcements |
| 0100–0145 | "V1": events, jobs, invoices v2, SMS, initiatives, security swaps |
| 0146–0161 | Hardening: attendance tenant guards, auth RPCs, outbox claim, consent, onboarding |

Enforced in the database: append-only `big_ledger` and `audit_logs` (triggers), one verified payment per submission (unique index), one attendance row per event and member, one active commitment per task and member, job capacity, security-swap state transitions, invoice status vocabulary, integer-cent checks on treasury tables.

Not enforced in the database: tenant isolation at runtime (RLS exists on 43 tables but the connection role bypasses it; 12 tables have none), fine uniqueness per event and member, "excused and fined cannot both stand", legacy `members.role` vs `member_roles` agreement, migration content integrity.

Money columns still `NUMERIC(10,2)`: `events.fine_amount`, `events.default_fine_amount`, `event_types.default_fine_amount`, `fines.amount` (frozen table).
</details>

<details><summary>▸ Frontend structure</summary>

| Piece | Files | Notes |
|---|---|---|
| Boot and state | `hooks/useAppData.ts` (composes 9 domain hooks) | Initial load fires 15 + 3N requests for N upcoming events |
| API | `api.ts` (722 lines: 5 fetch wrappers + all DTOs), `adapters.ts` (448) → `types.ts` | Pure mapper adapters are the one clean seam |
| Modules | `EventsModule.tsx` 1222, `FinanceModule.tsx` 849, `InitiativesModule.tsx` 527, `AttendanceModule.tsx` 414, `CommandModule.tsx` 403, `RosterModule.tsx` 392 | Business logic lives inside these |
| Auth | token in `localStorage`, permissions from `GET /api/rbac/me/permissions`, `can()` helper | `isOfficer` still used in 57 places |
| Pure helpers | `lib/*.ts` with node:test | dues, balance, consent, transaction, rollCall |

`tsconfig.json` has no `strict`. The frontend layout described in `LocalDev/CLAUDE.md` (`app/`, `components/modules/`, `lib/api-client.ts`, `lib/contracts/`) does not exist.
</details>

<details><summary>▸ Dependency directions</summary>

Intended: route → same-domain service → platform → RPC. Actual cross-domain imports: every domain → rbac; events → announcements, attendance; treasury → attendance; memberadmin → treasury; calendar → events, treasury, instrumentation; cron → announcements, auth, treasury; chapters → private helpers in auth. One cycle: `announcements ↔ cron` (message templates live in `api/cron/core`, the wrong package).
</details>

<details><summary>▸ Deployment and runtime</summary>

Vercel routes `/api/*` and `/c/*` to `api/index.py`; everything else to the static build. No `maxDuration` is set. A boot guard (`production_config_violations`) refuses to start with dev secrets, but only when `VERCEL_ENV` is production or preview. Email goes out through Gmail SMTP, SMS through Twilio, both from the cron drain. `Prod/api` is a hand-copied snapshot: 19 files differ from `LocalDev/api` and 21 are missing. `Prod/migrations` has 2 files. The production migration state is not recorded anywhere in git.
</details>
## 3 · Findings

**In short:** 68 findings, grouped by root cause (107 raw reports from eight audits and the lead were merged). Each card has the same six lines. Instances of the same root cause are listed inside one card, not as separate findings. Three reports were refuted and dropped; they are listed at the end of this section.

Reading a card: **What happens** is the observed behaviour. **How it goes wrong** is a concrete sequence. **Fix** gives the direction and the size of the change (surgical = one guard; small = one file or function; medium = a few files or one RPC; architectural = a pattern across the codebase).

### 🟠 P1 — 27 findings

| ID | Subsystem | One line | Confidence | Fix size |
|---|---|---|---|---|
| [F-002](#f-002) | attendance and standin | Same-day future events are counted as missed before they start | confirmed | medium |
| [F-003](#f-003) | attendance check-in se | Ambiguous attendance-session bindings fail open and can extend public check-in beyond clos | confirmed | medium |
| [F-004](#f-004) | attendance/treasury | An approved excuse and an event fine can both stand, and nothing in the database stops a s | confirmed | small |
| [F-005](#f-005) | auth | Unused setup and reset codes stay valid after password changes and do not revoke the curre | confirmed | surgical |
| [F-037](#f-037) | auth email notificatio | Failed setup/reset rows retain plaintext credentials indefinitely and Retry ignores creden | confirmed | medium |
| [F-006](#f-006) | chapters/rbac | Roster CSV import stamps members.role=officer for every non-member catalog role | confirmed | surgical |
| [F-007](#f-007) | configuration/authenti | The production safety guard is disabled on any non-Vercel deployment | confirmed | small |
| [F-008](#f-008) | database | Supabase anon/authenticated roles hold DML on non-RLS tables via the Data API | speculative | surgical |
| [F-010](#f-010) | deployment | Production deployment and DB state are not reproducible from the repo | confirmed | medium |
| [F-011](#f-011) | events / attendance | Autocommitted Python workflows leave event and attendance state half-applied | confirmed | architectural |
| [F-012](#f-012) | events lifecycle | Event deletion is an incoherent hard-delete path that either fails or destroys/strands dep | confirmed | architectural |
| [F-013](#f-013) | events notifications | The one-hour event-notification cooldown is a check-then-insert race | confirmed | small |
| [F-014](#f-014) | frontend/finance | Finance 'Add transaction' actions never persist | confirmed | small |
| [F-015](#f-015) | memberadmin standing | Standing ignores every unpaid fine when a chapter has no past required event | confirmed | small |
| [F-017](#f-017) | notifications/SMS deli | Inline SMS dispatch bypasses the atomic claim protocol and can race the cron drain | confirmed | medium |
| [F-019](#f-019) | notifications/provider | Provider success is committed before delivery state, allowing retries to duplicate real me | confirmed | medium |
| [F-021](#f-021) | platform outbox / trea | The advertised transactional outbox is post-commit and suppresses arbitrary insert failure | confirmed | architectural |
| [F-022](#f-022) | rbac | Revoking the officer role through the RBAC API does not revoke officer permissions | confirmed | small |
| [F-023](#f-023) | rbac | roles:assign has no grant ceiling: an officer can grant admin/president/treasurer | confirmed | small |
| [F-024](#f-024) | standing / fines repor | A one-cent partial payment clears standing, because engagement counts only status='unpaid' | confirmed | small |
| [F-025](#f-025) | task lifecycle | The generic task-status endpoint bypasses the report/approve lifecycle and permits arbitra | confirmed | medium |
| [F-026](#f-026) | tasks/events/attendanc | Self-vs-other authorization compares a string id to a UUID and fails closed | confirmed | surgical |
| [F-027](#f-027) | treasury adjustments | Any officer can post a sub-$500 adjustment against their own member id, and it takes effec | confirmed | small |
| [F-028](#f-028) | treasury balance cache | Treasurer dashboard, balance CSV, and 'members with balance' SMS read member_finance_accou | confirmed | small |
| [F-029](#f-029) | treasury payments / al | Invoice coverage is stored two ways, and reallocating a payment that still has verified_pa | confirmed | small |
| [F-030](#f-030) | treasury refunds | A refund raises what the member owes and does not reopen an invoice, and the SPA can only  | confirmed | small |
| [F-031](#f-031) | treasury schema / bala | The tables balances are computed from can be updated in place; the append-only ledger is n | confirmed | medium |

<a id="f-002"></a>
#### F-002 · 🟠 P1 · confirmed · attendance and standing
**Same-day future events are counted as missed before they start**

- **What happens:** At midnight, every required event scheduled later that day enters attendance and standing denominators. Members without early check-ins or approved excuses are immediately treated as absent.
- **Where:** `api/memberadmin/core/engagement.py:42-49 (load_member_engagement)`, `api/memberadmin/core/engagement.py:108-127 (load_member_engagement)`, `api/attendance/services/signals.py:14-68 (attendance_summary)`, `api/memberadmin/core/standing_rules.py:27-50 (derive_standing)`
- **How it goes wrong:** 1. Schedule three required events for 8 PM today. 2. At 9 AM, request standings. 3. Every member without attendance rows has three unexcused absences. 4. `derive_standing` returns `delinquent` before any event begins.
- **Why it matters / blast radius:** Standing can deteriorate before members have had an opportunity to attend, and attendance percentages shown during the day are false. — Every required event on its calendar date, affecting chapter-wide attendance summaries, engagement scores, and standing.
- **Tests catch it?** No. `tests/events/test_attendance_summary.py` covers prior days and a future day, but no event later on the current day.
- **Fix:** Define one authoritative event-completion timestamp using an explicit chapter timezone and include an event only after that timestamp. Reuse the predicate in attendance summary, engagement, and fine eligibility. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Cursor/Grok: Standing counts a required event as an unexcused absence for
- **Lead note:** Standing counts same-day future events as missed.

<a id="f-003"></a>
#### F-003 · 🟠 P1 · confirmed · attendance check-in sessions
**Ambiguous attendance-session bindings fail open and can extend public check-in beyond closes_at**

- **What happens:** An open manual session followed by a short-link session can produce two sessions bound to one link. The validator treats that as ambiguous and skips the session close gate, leaving the public link valid until its independent TTL. Concurrent link creation can also leave multiple active links for one event because deactivation and insertion are separate autocommit transactions.
- **Where:** `api/attendance/services/checkin_links.py:88-133 (_session_for_link)`, `api/attendance/services/checkin_links.py:141-164 (_bind_open_sessions)`, `api/attendance/services/checkin_links.py:167-217 (create_checkin_link)`, `api/attendance/services/checkin_links.py:220-255 (validate_checkin_link)`
- **How it goes wrong:** 1. Create an open manual attendance session for an event. 2. Create a short-link session for the same event. 3. Link creation binds the manual session, then session creation inserts a second bound session. 4. Let both `closes_at` values pass. 5. Submit the public code; `_session_for_link` returns `None`, so validation accepts it until link TTL.
- **Why it matters / blast radius:** Members can check in after an officer-defined session closes, and officers may see or distribute competing active codes. This corrupts the attendance record used by standing and fines. — Events using attendance sessions, particularly those mixing manual and short-link/QR modes; concurrent officers opening links are also affected.
- **Tests catch it?** Partial. `tests/attendance/test_checkin_links_unit.py` expects ambiguity to return `None` and separately tests one closed bound session, but never verifies that ambiguous bindings fail closed. `tests/attendance/test_checkin_flow.py` covers sequential
- **Fix:** Move link/session creation into one locked RPC. Add a partial unique index for one active link per event and a uniqueness/cardinality rule for `attendance_sessions.checkin_link_id`. Treat multiple bound sessions as invalid/fail-closed, and apply the same session gate to active-link reads. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1

<a id="f-004"></a>
#### F-004 · 🟠 P1 · confirmed · attendance/treasury
**An approved excuse and an event fine can both stand, and nothing in the database stops a second fine for the same event and member**

- **What happens:** The manual issue path (POST /api/fines/issue) refuses members who are checked in or have an approved excuse, and uses idempotency key fine:{event}:{member} on tr_create_invoice_v2. Marking attendance excused writes the approved excuse and leaves every fine invoice in place. Excuse review voids one unpaid fine and leaves partially_paid fines and any second unpaid fine. Check-in upserts checked_in=true and does not void a fine. There is no unique index on (source_event_id, member_id) for live fine
- **Where:** `migrations/0146_attendance_tenant_guards.sql:175-193 (at_set_attendance excused branch)`, `migrations/0146_attendance_tenant_guards.sql:278-288 (at_review_excuse)`, `migrations/0010_treasury_receivables_tables.sql:14-29 (unpaid_invoices.source_event_id index, not unique)`, `api/treasury/api/fines_legacy.py:65-73 (_already_fined_ids)`
- **How it goes wrong:** 1. Treasurer POST /api/fines/issue for member M on required event E after the 24h gate; tr_create_invoice_v2 inserts an unpaid $25 fine. 2. Officer POST /api/attendance/event/E/manual/M with status excused; at_set_attendance inserts an approved excuse and does not void the invoice. 3. M now has an approved excuse and an unpaid fine; standing still counts UNPAID_FINES. 4. Separately, two concurrent POST /api/fines/process-event/E calls both pass the read-then-write dedup in process_event_fines (null idempotency key) and insert two fines; PUT /api/excuses/{id}/review voids only the first unpaid row.
- **Why it matters / blast radius:** Standing and the member's balance both treat an unpaid kind='fine' invoice as money owed. The product rule that an excused member is not fined is true only for the review-excuse path, and only for a single unpaid invoice. Two issuance RPCs (tr_create_invoice from process_event_fines with a null idem — Every required-event fine, standing, and the member balance cache for that invoice. Waiving via the treasurer void route still works; the attendance-excused path does not.
- **Tests catch it?** partial. tests/attendance/test_tenant_guards.py::test_approve_after_fine_processing_voids_the_invoice covers at_review_excuse on one unpaid invoice. No test asserts at_set_attendance excused voids a fine, that partially_paid fines are voided, or that
- **Fix:** Add a partial unique index on unpaid_invoices (source_event_id, member_id) WHERE kind='fine' AND status <> 'cancelled'. Call the same void used by at_review_excuse from the excused branch of at_set_attendance, and void every open (unpaid or partially_paid) fine for that pair. Keep the 24h and audience checks, but do not rely on a prior SELECT for uniqueness. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Codex: Attendance, excuses, and fine waivers do not share a coheren
- **Lead note:** Excuse/attendance/fine state machine incoherent.

<a id="f-005"></a>
#### F-005 · 🟠 P1 · confirmed · auth
**Unused setup and reset codes stay valid after password changes and do not revoke the current session**

- **What happens:** A setup or reset code is a bearer credential for 7 days. Setting a password bumps token_version and kills JWTs minted earlier, but every still-unused code remains redeemable. Redemption mints a JWT at the member's current token_version and leaves other live sessions in place. Issuing a reset does not burn older unused codes. An officer with members:invite (the officer role has that key since migration 0147) receives the plaintext code in the HTTP body as well as email.
- **Where:** `api/auth/api/auth.py:398-468 (redeem_setup_code)`, `api/auth/api/auth.py:302-320 (set_password)`, `api/auth/api/auth.py:472-510 (issue_reset_code)`, `migrations/0148_auth_hardening.sql:119-140 (au_set_password)`
- **How it goes wrong:** 1. Officer POST /api/auth/reset-code/{victim_id} with Authorization: Bearer <officer jwt> → 200 {setup_code}. token_version becomes N. 2. Victim POST /api/auth/login with their password, then POST /api/auth/set-password → token_version N+1; the reset code row is still used_at NULL. 3. Holder of the code POST /api/auth/redeem-setup-code {email, code} → 200 access_token whose ver equals N+1. 4. GET /api/auth/me with that token is the victim; the victim's post-password token still works until someone bumps the epoch again. The same sequence works for any unused invite code that was not the one the member redeemed.
- **Why it matters / blast radius:** token_version is the only server-side revocation control. An unused code is a second login that ignores it, so a password change does not close a code that was already issued, and redeeming that code does not kick the legitimate session. — Any member who has an outstanding code (every invite, every officer reset, every chapter-create and roster-import code returned in JSON). Parallel access for up to 7 days after the member believes the
- **Tests catch it?** no. tests/auth/test_tokens.py asserts a bumped ver kills old JWTs. tests/auth/test_invite_setup_codes.py asserts reset bumps token_version and that the new code redeems. Neither redeems a leftover code after set-password, nor checks that sibling code
- **Fix:** In au_set_password and au_bump_token_version, set used_at=now() on every unconsumed member_setup_codes row for that member. On successful au_consume_setup_code, increment token_version and return it so the new JWT is the only live session. · scope: **surgical**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1

<a id="f-037"></a>
#### F-037 · 🟠 P1 · confirmed · auth email notifications
**Failed setup/reset rows retain plaintext credentials indefinitely and Retry ignores credential expiry**

- **What happens:** A failed row stores a live code for up to seven days and retains it after expiry indefinitely. An officer can later retry it, causing an expired or already-used code to be emailed. The officer UI hides the body, but the plaintext remains in the database.
- **Where:** `api/auth/notifications.py:31-59 (notify_code)`, `api/cron/services/outbox_drain.py:171-189 (_close_row)`, `api/announcements/services/outbox.py:130-170 (retry_outbox_row)`, `migrations/0148_auth_hardening.sql:67-79 (member_setup_codes)`
- **How it goes wrong:** 1. An officer issues a reset code. 2. SMTP is unavailable, so the row fails and keeps the plaintext. 3. The member redeems the code through another channel, or seven days pass. 4. An officer retries the failed row. 5. The drain emails the obsolete code and only then wipes the payload.
- **Why it matters / blast radius:** This expands credential exposure from one-time issuance to durable database storage and sends confusing invalid credentials during recovery. A database read compromise during the validity window reveals usable setup/reset codes. — All failed SETUP_CODE and RESET_CODE messages.
- **Tests catch it?** partial — tests/cron/test_drain_email.py::test_a_failed_setup_code_row_keeps_its_payload explicitly verifies retention, and sent/simulated wiping is covered. No test covers expiry, redemption, cleanup, or Retry of an obsolete code.
- **Fix:** Store an encrypted delivery artifact or regenerate a fresh code on retry. Add an expiry check before rendering, terminally redact expired/used credentials, and enforce a retention policy for failed secret-bearing rows. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: upgraded P0
- **Lead note:** Refuter (Gemini) upgraded P2→P0. Lead sets P1: exposure needs database read access and codes expire; still live credentials in plaintext in failed outbox rows.

<a id="f-006"></a>
#### F-006 · 🟠 P1 · confirmed · chapters/rbac
**Roster CSV import stamps members.role=officer for every non-member catalog role**

- **What happens:** A row with role=treasurer, role=social_chair, or role=alumni_advisor is stored as legacy officer plus that one member_roles key. After the invitee redeems the setup code returned in the import response, they hold the entire officer permission set from migration 0147 (members:invite, roles:assign, treasury:payment:verify, treasury:refund:create, attendance:override, and the rest) in addition to the narrow catalog role. role=member and a blank role stay member. The roster column shows Officer, not
- **Where:** `migrations/0157_sms_consent.sql:45-65 (ch_import_roster)`, `api/chapters/services/onboarding.py:118-141 (parse_roster_csv)`, `api/rbac/services/permissions.py:23-29 (_effective_role_keys)`, `tests/chapters/test_roster_import.py:63-77 (test_optional_role_column_grants_the_catalog_role)`
- **How it goes wrong:** 1. Officer with members:invite POSTs multipart CSV to /api/chapters/{chapter_id}/roster with a row name,email,phone,social_chair (or alumni_advisor). 2. Response includes that row's setup_code. 3. Redeem the code, set a password. 4. GET /api/rbac/me/permissions includes roles:assign and treasury:refund:create. 5. POST /api/rbac/members/{self}/roles {role_key:"admin"} succeeds.
- **Why it matters / blast radius:** The catalog's least-privilege roles are real only when assigned through rbac_assign_role. The spreadsheet path that officers are told to use promotes every titled row to a full officer, including the ability to grant admin. That is a different mechanism from explicitly putting admin in the CSV. — Every invited row whose CSV role is anything other than member or empty. One import can create many such accounts, and the plaintext codes come back to the uploader.
- **Tests catch it?** no. tests/chapters/test_roster_import.py::test_optional_role_column_grants_the_catalog_role checks member_roles only.
- **Fix:** Set members.role to officer only when role_key is officer (or null/member → member). Grant the catalog key solely via member_roles. Assert members.role in the treasurer import test. · scope: **surgical**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1

<a id="f-007"></a>
#### F-007 · 🟠 P1 · confirmed · configuration/authentication
**The production safety guard is disabled on any non-Vercel deployment**

- **What happens:** Docker, bare uvicorn, another serverless provider, or a misconfigured Vercel-like environment can serve with the known JWT secret and passwordless dev login enabled.
- **Where:** `api/config.py:52-60 (is_deployed)`, `api/index.py:27-38 (production_config_violations)`, `api/auth/api/auth.py:272-299 (dev_login)`, `tests/config/test_production_guard.py:187-190 (test_dev_is_never_guarded)`
- **How it goes wrong:** 1. An operator deploys `uvicorn api.index:app` outside Vercel with VERCEL_ENV unset and DEV_AUTH_BYPASS=true. 2. The guard returns no violations. 3. An attacker POSTs an active member email to `/api/auth/dev-login`. 4. The API returns a valid JWT signed with the default secret.
- **Why it matters / blast radius:** An internet-reachable alternative deployment can let anyone who knows an active email mint a seven-day member token, and the known JWT secret permits token forgery. — Complete authentication bypass for the affected deployment.
- **Tests catch it?** yes, but codifies the unsafe scope — tests/config/test_production_guard.py::test_dev_is_never_guarded.
- **Fix:** Use an explicit `APP_ENV=local|test|preview|production` and fail closed when ambiguous. Enable dev-login only under an explicit local-development flag plus loopback/network restriction, not by absence of Vercel metadata. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Cursor/Grok: Auth boot guard, dev-login lock, and the chapter-signup IP l; Codex: Production boot validation omits BASE_URL despite two securi
- **Lead note:** Production guard depends on VERCEL_ENV; BASE_URL not validated.

<a id="f-008"></a>
#### F-008 · 🟠 P1 · speculative · database
**Supabase anon/authenticated roles hold DML on non-RLS tables via the Data API**

- **What happens:** Depends on a dashboard toggle outside the repo
- **Where:** `migrations/0153_auth_rpc_execute_revoke.sql:1-12, 50-122`, `docs/adr/0002`
- **How it goes wrong:** 1. Data API enabled. 2. anon key → GET /rest/v1/members.
- **Why it matters / blast radius:** Cross-tenant read of password hashes and setup codes — All
- **Tests catch it?** No
- **Fix:** Revoke DML from anon/authenticated; verify the Data API is off · scope: **surgical**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P1
- **Lead note:** Salvaged claim; depends on Supabase Data API toggle outside the repo. Refuter (Codex) confirmed the mechanism; D1 notes no GRANT on tables appears in the repo, so this depends on Supabase default privileges and the Data API toggle. Verify in the dashboard; revoking DML from anon/authenticated is cheap either way.

<a id="f-010"></a>
#### F-010 · 🟠 P1 · confirmed · deployment
**Production deployment and DB state are not reproducible from the repo**

- **What happens:** Nobody can tell which code or schema production runs from git alone
- **Where:** `Prod/api (drifted snapshot)`, `Prod/migrations (2 files)`, `scripts/db_guard.py (PROD_PROJECT_REFS empty)`, `LocalDev/CLAUDE.md`
- **How it goes wrong:** 1. Fix a bug in LocalDev. 2. Deploy Prod/ (hand-copied). 3. Prod DB lacks migrations the code assumes → runtime errors on real user data.
- **Why it matters / blast radius:** The 2026-09-29 auth fixes, outbox claim, consent and onboarding are absent from Prod/api; a prod incident cannot be reproduced locally — All production users
- **Tests catch it?** No
- **Fix:** Make Prod a build artifact of LocalDev (or a symlink/CI copy), populate PROD_PROJECT_REFS, record prod migration state · scope: **medium**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P1 · **also reported as:** Gemini Pro: Production frontend codebase heavily diverged and missing ma

<a id="f-011"></a>
#### F-011 · 🟠 P1 · confirmed · events / attendance
**Autocommitted Python workflows leave event and attendance state half-applied**

- **What happens:** A later validation, insert, audit, or database failure does not roll back earlier steps. `create_session` also calls a helper that acquires its own global `get_db()` client rather than using the supplied client, making an encompassing transaction impossible.
- **Where:** `api/platform/postgres.py:169-186 (QueryBuilder.execute)`, `api/events/services/events.py:527-598 (update_event)`, `api/attendance/services/checkin_links.py:167-217 (create_checkin_link)`, `api/attendance/services/sessions.py:16-72 (create_session)`
- **How it goes wrong:** 1. An officer updates an event and supplies a custom audience. 2. The scalar event update commits. 3. `ev_set_audience` rejects one cross-chapter member or the DB connection fails. 4. The API errors, but the title/time/visibility remains changed and the old audience remains. A parallel sequence can deactivate the only check-in link before the replacement insert fails.
- **Why it matters / blast radius:** These are state-machine transitions whose intermediate states are observable: updated visibility with an old audience, no active check-in link, an orphan active link, an unpointed session, or a requeued message without its required audit. — Individual events, attendance sessions, active door links, and retried messages; concurrent users can act on the intermediate state.
- **Tests catch it?** partial — `tests/events/test_supervisors.py` covers successful event updates; `tests/attendance/test_checkin_flow.py` covers successful session/link binding; `tests/attendance/test_checkin_links_unit.py` verifies insert errors fail fast but does not 
- **Fix:** Implement `ev_update_event`, attendance-session creation/link rotation, and outbox retry as transactional RPCs. At minimum, pass one explicit transaction-capable client through helpers and add phase-by-phase failure tests. · scope: **architectural**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Codex: Event field updates commit before custom-audience validation; Codex: Task capacity is patched after creation in a second transact; lead session: Chapter creation and roster import can half-apply
- **Lead note:** General pattern: autocommitted Python multi-step writes; 24/82/64 are instances.

<a id="f-012"></a>
#### F-012 · 🟠 P1 · confirmed · events lifecycle
**Event deletion is an incoherent hard-delete path that either fails or destroys/strands dependent workflow state**

- **What happens:** An event without guarded audit children can be erased, cascading attendance/excuses while turning jobs and fine invoices into parentless records. A notified event, an event with swap history, or an event with a security task can instead fail deletion at the database boundary.
- **Where:** `api/events/api/events.py:128-147 (delete_event)`, `migrations/0001_initial_schema.sql:74-108 (attendance and excuses foreign keys)`, `migrations/0010_treasury_receivables_tables.sql:5-20 (unpaid_invoices.source_event_id)`, `migrations/0110_tasks_v1_commitments.sql:8-15 (tasks.event_id)`
- **How it goes wrong:** 1. Create a required event, record attendance, create jobs, and issue a fine. 2. Call `DELETE /api/events/{id}`. 3. Attendance/excuses disappear while the fine and standard jobs survive without an event reference. 4. Repeat with a notified event or security swap; the delete is rejected by an append-only trigger instead.
- **Why it matters / blast radius:** The same authorized request has radically different effects based on hidden history. Successful deletion destroys attendance evidence and disconnects financial/job records; failed deletion exposes an unusable cancellation workflow. — All event-linked attendance, excuses, check-in sessions, organizers, supervisors, jobs, security assignments/swaps, notification history, and fine attribution.
- **Tests catch it?** No. Repository-wide test search found no event-delete lifecycle test covering dependent rows or append-only trigger failures.
- **Fix:** Replace hard deletion with an explicit atomic cancellation RPC and cancellation state. Define reconciliation rules for jobs, attendance, check-in links, pending swaps, notifications, and fines; reserve physical deletion for empty draft events. · scope: **architectural**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Codex: Hard-deleting an event either erases attendance evidence or 

<a id="f-013"></a>
#### F-013 · 🟠 P1 · confirmed · events notifications
**The one-hour event-notification cooldown is a check-then-insert race**

- **What happens:** Two concurrent notify calls can both observe no recent send, create distinct send rows, and fan out distinct outbox messages to every recipient.
- **Where:** `api/events/services/notifications.py:128-178 (notify_event)`, `migrations/0145_security_swaps_v1.sql:954-1078 (ev_notify_event)`, `greekos/src/hooks/useEvents.ts:351-380 (handleSendEventNotifyBlast)`, `tests/events/test_notify.py:84-175 (notify and cooldown tests)`
- **How it goes wrong:** 1. Two officers preview a complete event. 2. Both submit notify requests concurrently. 3. Each transaction passes the cooldown query before either inserts. 4. Both create a send and recipient outbox rows. 5. The drain delivers two blasts.
- **Why it matters / blast radius:** A double click, retry, or two officers can generate duplicate chapter-wide SMS blasts. Distinct send IDs defeat outbox deduplication, creating direct messaging cost and reputational impact. — Every SMS-reachable active member in the chapter per raced notification.
- **Tests catch it?** No. `tests/events/test_notify.py` covers one happy send and a sequential send after an expired cooldown, not concurrent first sends.
- **Fix:** Serialize on the event row or an advisory lock inside `ev_notify_event`, then check and insert. Also have the UI/API generate and send an idempotency key for each confirmation action. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1

<a id="f-014"></a>
#### F-014 · 🟠 P1 · confirmed · frontend/finance
**Finance 'Add transaction' actions never persist**

- **What happens:** Officer records a payment/invoice/adjustment in the UI, sees 'Recorded …', nothing reaches the backend
- **Where:** `greekos/src/hooks/useFinance.ts:169-310 (handleRecordPayment, handlePostInvoice, handleApproveFinePayment, handlePostLedgerCorrection)`, `greekos/src/components/FinanceModule.tsx:155-215, 707-712`
- **How it goes wrong:** 1. Officer opens Finance > Add transaction > Payment. 2. Fills amount, submits. 3. Toast 'Recorded payment'. 4. Reload: payment gone; member still owes.
- **Why it matters / blast radius:** Treasurer believes money was recorded; balances and ledger on the server disagree with what the UI showed — Every chapter using the finance tab
- **Tests catch it?** No — no frontend test covers these handlers
- **Fix:** Wire each handler to the treasury API or remove the UI actions; add a test that asserts a network call · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P1 · **also reported as:** Gemini Pro: Financial transactions mutate React state without backend pe; Cursor/Grok: Standing changes and add-member succeed only in React state;
- **Lead note:** D5 rated P0; lead keeps P1 (no data loss, but money the UI claims recorded is not). 80 is the same pattern in roster.

<a id="f-015"></a>
#### F-015 · 🟠 P1 · confirmed · memberadmin standing
**Standing ignores every unpaid fine when a chapter has no past required event**

- **What happens:** Fine aggregation is incorrectly conditional on attendance history. A new or off-season chapter with no qualifying required event reports zero fine debt for every member, regardless of unpaid fine invoices.
- **Where:** `api/memberadmin/core/engagement.py:42-66 (load_member_engagement)`, `api/memberadmin/core/engagement.py:87-127 (load_member_engagement)`, `api/memberadmin/services/standing.py:14-35 (compute_member_standings)`, `tests/memberadmin/test_engagement_fines.py:27-35 (_make_required_event)`
- **How it goes wrong:** 1. Create a chapter with active members but no past required event. 2. Issue or import an unpaid fine invoice for a member. 3. Request member standings or engagement scores. 4. The loader returns zero fines and the member remains `good_standing`.
- **Why it matters / blast radius:** Standing is an authorization and governance signal. Members with active fine debt can be presented as in good standing until the chapter has at least one required event in the past. — All members in chapters with no required event satisfying the date predicate; especially newly provisioned chapters and chapters between terms.
- **Tests catch it?** No. `tests/memberadmin/test_engagement_fines.py` deliberately creates a past required event in every fine-related test, so it never exercises the early return.
- **Fix:** Load fine invoices independently of required events. Treat attendance aggregation as optional, but always merge treasury aggregates into the member result. Add a zero-required-events plus unpaid-fine regression test. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1

<a id="f-017"></a>
#### F-017 · 🟠 P1 · confirmed · notifications/SMS delivery
**Inline SMS dispatch bypasses the atomic claim protocol and can race the cron drain**

- **What happens:** The cron worker is protected against another cron worker, but not against the synchronous dispatcher running in the original HTTP request. An inline dispatcher can retain a pending-row snapshot while the cron claims and sends the same row.
- **Where:** `api/announcements/services/sms.py:214-269 (dispatch_send)`, `api/announcements/services/sms.py:280-317 (_dispatch_twilio_row)`, `api/events/services/notifications.py:154-178 (notify_event)`, `api/cron/services/outbox_drain.py:284-315 (drain_outbox)`
- **How it goes wrong:** 1. An officer POSTs `/api/announcements/{id}/send-sms`; the RPC commits pending rows. 2. `dispatch_send` selects those rows. 3. Before its Twilio call completes, the five-minute cron invokes `outbox_claim_batch` and changes the same rows to `sending`. 4. The inline request and cron both POST the messages to Twilio. 5. Each member receives the same blast twice.
- **Why it matters / blast radius:** A slow or interrupted manual blast can double-text an entire chapter. The very claim protocol introduced to prevent overlapping delivery is bypassed by one of the two production delivery paths. — ANNOUNCEMENT_SMS and EVENT_NOTIFY batches; potentially every SMS recipient in a chapter.
- **Tests catch it?** partial — tests/cron/test_drain_outbox.py::test_a_claimed_row_is_not_handed_to_a_second_worker proves claim-versus-claim exclusion, but no test races `dispatch_send` against `drain_outbox`. tests/announcements/test_sms_send.py and tests/events/test_n
- **Fix:** Use one delivery owner. Prefer having send endpoints commit queued rows and return immediately, leaving all delivery to `outbox_claim_batch`. If inline delivery is required, claim only that send's rows through the same RPC before contacting Twilio. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Codex: Interactive SMS blasts perform sequential blocking provider ; Cursor/Grok: Announcement SMS and event notify are sent inline and also l; Codex: SMS parent send logs can be changed from failed or empty to 
- **Lead note:** Inline SMS dispatch duplicating/racing the outbox drain; 3/4/5 are facets.

<a id="f-019"></a>
#### F-019 · 🟠 P1 · confirmed · notifications/provider delivery
**Provider success is committed before delivery state, allowing retries to duplicate real messages**

- **What happens:** External delivery and local acknowledgement are two separate, non-idempotent operations. A successful provider request followed by a database failure is indistinguishable from an unsent abandoned claim and is retried.
- **Where:** `api/cron/services/outbox_drain.py:207-249 (_deliver_sms, _deliver_email)`, `api/cron/services/outbox_drain.py:252-281 (_deliver_row)`, `api/announcements/services/sms.py:300-317 (_dispatch_twilio_row)`, `api/announcements/services/twilio_client.py:38-66 (send_sms)`
- **How it goes wrong:** 1. Cron claims a row. 2. Twilio or SMTP accepts and sends it. 3. The database update marking the row `sent` fails. 4. The row remains `sending`. 5. Fifteen minutes later the reaper returns it to `pending`. 6. A later cron sends the message again.
- **Why it matters / blast radius:** This is an at-least-once system presented as exactly-once. Duplicate payment, assignment, credential, or chapter-wide messages can occur during ordinary transient database failures. — All real SMS and email event types; up to the entire 100-row batch during a database interruption.
- **Tests catch it?** no — tests/cron/test_drain_outbox.py and tests/cron/test_drain_email.py mock providers and assume the subsequent database close succeeds; no test simulates provider success followed by `_close_row` failure.
- **Fix:** Persist provider message IDs and separate `accepted` from confirmed delivery. Supply a stable provider idempotency key where supported. At minimum, park ambiguous post-send failures for operator reconciliation instead of automatically reaping them into another send. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1

<a id="f-021"></a>
#### F-021 · 🟠 P1 · confirmed · platform outbox / treasury notifications
**The advertised transactional outbox is post-commit and suppresses arbitrary insert failures**

- **What happens:** Financial or account state can commit without a corresponding outbox row. A constraint error, missing table, connection failure, serialization issue, or pool failure is indistinguishable from a duplicate dedup key and is not logged by the shared enqueue layer.
- **Where:** `api/platform/outbox.py:70-107 (enqueue)`, `api/platform/outbox.py:110-177 (enqueue_many)`, `api/treasury/services/invoices.py:62-104 (create_invoice_v2)`, `api/treasury/notifications.py:1-25 (outbox contract documentation)`
- **How it goes wrong:** 1. `tr_create_invoice_v2` commits the invoice, ledger, and audit rows. 2. The subsequent outbox insert fails because the connection drops or the schema is incompatible. 3. `enqueue` returns `None`. 4. The route returns the created invoice. 5. No pending message exists for cron to retry.
- **Why it matters / blast radius:** A missing row cannot be recovered by the drain worker. Invoice, payment, refund, event, and setup-code messages can be permanently absent while the initiating request reports success. — All Python-enqueued email notifications, including treasury lifecycle messages, event emails, setup/reset codes, and bulk fan-out notifications.
- **Tests catch it?** partial — `tests/treasury/test_chunkG_rebuild_hardening.py` tests successful persistence and duplicate deduplication; `tests/auth/test_code_emails.py` tests a wrapper logging a raised enqueue error. Neither test injects a non-UNIQUE failure inside `a
- **Fix:** Move business-state and outbox insertion into the same RPC transaction. Where that is not immediately possible, use `INSERT ... ON CONFLICT (dedup_key) DO NOTHING RETURNING *`, suppress only `UniqueViolation`, log/raise every other error, and add failure-injection tests. · scope: **architectural**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** Codex: Outbox enqueue treats every insert failure as a harmless ded
- **Lead note:** Outbox enqueue swallows every insert failure as dedup.

<a id="f-022"></a>
#### F-022 · 🟠 P1 · confirmed · rbac
**Revoking the officer role through the RBAC API does not revoke officer permissions**

- **What happens:** PUT /api/members/{id}/role?role=member demotes both stores and is what tests/rbac/test_legacy_role_sync.py locks. DELETE /api/rbac/members/{id}/roles/officer, which is what the roster role panel calls, removes only the member_roles row. If members.role is still 'officer' — the state ch_create_chapter, promotion, and the 0147 backfill all create — the resolver keeps granting the full officer set (roles:assign, treasury:payment:verify, treasury:refund:create, members:invite, and the rest of the 01
- **Where:** `api/rbac/core/policy.py:15-18 (LEGACY_ROLE_COMPAT)`, `api/rbac/services/permissions.py:23-29 (_effective_role_keys)`, `migrations/0083_rbac_seed_rpcs.sql:257-291 (rbac_revoke_role)`, `migrations/0154_mem_set_legacy_role.sql:44-53 (mem_set_legacy_role)`
- **How it goes wrong:** 1. Chapter officer (members.role=officer and a member_roles officer row) opens the role panel and switches officer off. 2. DELETE /api/rbac/members/{id}/roles/officer → 200, checkbox clears. 3. That member calls POST /api/treasury/payments/submissions/{id}/verify-v1 or POST /api/rbac/members/{self}/roles {role_key:admin}. 4. require_permission still passes because LEGACY_ROLE_COMPAT adds officer. 5. Separately, the last real officer PUT /api/members/{self}/role?role=member and the chapter has nobody left who can assign roles.
- **Why it matters / blast radius:** The UI for role changes tells the officer the revoke worked. Authorization still treats the member as an officer. That is the bug 0154 fixed on one writer and left in place on the writer the product actually clicks. — Every demotion done from MemberRolesPanel. Permissions that 0147 attached to officer, including roles:assign (already the grant-ceiling issue) and payment verification, survive. Chapter lockout if the
- **Tests catch it?** no for the DELETE path. tests/rbac/test_legacy_role_sync.py covers PUT only, and test_demotion_leaves_separately_granted_roles_alone intentionally keeps stackable roles such as treasurer after PUT demotion. Nothing calls rbac_revoke_role and then get
- **Fix:** Make rbac_revoke_role of role_key officer also set members.role=member when that was the legacy value, in the same statement, or stop consulting LEGACY_ROLE_COMPAT once member_roles is authoritative. Refuse to remove the last roles:assign holder. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Cursor/Grok: Revoking the officer role through rbac_revoke_role leaves me; Cursor/Grok: is_officer treats every catalog role except member as an off
- **Lead note:** LEGACY_ROLE_COMPAT keeps members.role=officer authoritative after RBAC revoke; is_officer over-broad.

<a id="f-023"></a>
#### F-023 · 🟠 P1 · confirmed · rbac
**roles:assign has no grant ceiling: an officer can grant admin/president/treasurer**

- **What happens:** Any holder of roles:assign can escalate to any role
- **Where:** `migrations/0147_authority_one_gate.sql:51-72`, `migrations/0083_rbac_seed_rpcs.sql:54, 203-254`
- **How it goes wrong:** 1. Officer with roles:assign calls POST /api/rbac/assign for self with role admin. 2. Now admin.
- **Why it matters / blast radius:** Privilege escalation to full admin — All chapters
- **Tests catch it?** Unknown
- **Fix:** Add a grant ceiling (can only grant roles you hold or below) · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P1

<a id="f-024"></a>
#### F-024 · 🟠 P1 · confirmed · standing / fines reporting
**A one-cent partial payment clears standing, because engagement counts only status='unpaid' fines at face value**

- **What happens:** Standing and the engagement score see a fine only while its status is exactly unpaid, and they charge the full face amount. The first verified dollar that moves the row to partially_paid drops the fine out of standing entirely. The fine summary still books the whole face amount as unpaid. The SPA fine list shows a waived (cancelled) fine as Paid.
- **Where:** `api/memberadmin/core/engagement.py:87-128 (load_member_engagement)`, `api/memberadmin/core/standing_rules.py:27-50 (derive_standing)`, `api/memberadmin/services/standing.py:14-35 (compute_member_standings)`, `api/treasury/api/fines_legacy.py:275-298 (fine_summary)`
- **How it goes wrong:** 1. Officer issues a $25 fine via POST /api/fines/issue. status=unpaid. GET standing returns warning (unpaid_count=1). 2. Member POSTs /api/treasury/payments/submissions or a balance submission for 1 cent. 3. Officer POSTs verify-v1. tr_verify_payment_v2 allocates 1 cent, tr_refresh_invoice_status sets partially_paid because remaining < amount and remaining > 0. 4. engagement's unpaid filter misses the row. derive_standing returns good_standing. 5. GET /api/fines/summary still adds 2500 to total_unpaid_cents. The reminder endpoint would text the real 2499 remaining.
- **Why it matters / blast radius:** Standing is the delinquency gate (good / warning / delinquent) and it feeds the roster balance the fake finance handlers also mutate. A member with one $25 fine is in warning; a $0.01 verified payment against that fine (claimed_amount_cents CHECK is only > 0) makes it partially_paid and returns them — Every chapter's standing board, engagement scores, and the fine summary/SPA fine list. Dues invoices are already ignored by standing (kind=fine only); this hole is specifically fines that are partly c
- **Tests catch it?** no. No test under tests/ references partially_paid together with engagement or standing. tests that drive derive_standing pass counts in directly and never build a partially_paid invoice.
- **Fix:** Drive standing and fine_summary off the same remaining-cents helper send_reminder already uses (amount - direct verified payments - net allocations), and treat partially_paid as still owed. Map cancelled to waived in adaptFines, not Paid. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Cursor/Grok: Standing treats only status=unpaid fine invoices at their fu
- **Lead note:** Standing fine query only sees status=unpaid at full amount.

<a id="f-025"></a>
#### F-025 · 🟠 P1 · confirmed · task lifecycle
**The generic task-status endpoint bypasses the report/approve lifecycle and permits arbitrary reopening**

- **What happens:** An authorized caller can set an event or initiative job directly to `done` without report/review, cancel an in-progress job, or change an already approved/cancelled/done-reported task back to open/in-progress/done.
- **Where:** `api/tasks/api/schemas.py:47-50 (TaskStatusUpdate)`, `api/tasks/api/tasks.py:74-99 (update_task_status)`, `migrations/0145_security_swaps_v1.sql:885-947 (tk_update_task_status)`, `greekos/src/hooks/useTasks.ts:39-45 (handleToggleTaskStatus)`
- **How it goes wrong:** 1. Commit to an event job. 2. POST `/api/tasks/{id}/status` with `done`, skipping `tk_report_done` and `tk_approve_task`. 3. All commitments become completed without approver metadata. 4. A reviewer later posts `open` on an approved task, erasing its terminal state while approval timestamps remain.
- **Why it matters / blast radius:** Approval audit semantics and contribution credit can diverge from task status. Reopening terminal work or completing all claimants outside the approval RPC creates states the dedicated lifecycle RPCs try to prevent. — All non-security tasks reachable through the generic status route, including event, initiative, and standalone jobs.
- **Tests catch it?** Partial. `tests/tasks/test_jobs_lifecycle.py` verifies only that target values `done_reported` and `approved` are rejected; it does not test forbidden source-to-target transitions or metadata consistency.
- **Fix:** Define an explicit transition matrix in the live RPC. Restrict the simple open/done toggle to a distinct standalone-task type, or route every job through report/approve/reject. Clear or preserve terminal metadata according to explicit transition rules. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P1 · **also reported as:** lead session: Task-status ownership check fails open for unowned jobs

<a id="f-026"></a>
#### F-026 · 🟠 P1 · confirmed · tasks/events/attendance
**Self-vs-other authorization compares a string id to a UUID and fails closed**

- **What happens:** Omitting member_id commits the caller. Sending the caller's own id as a string is treated as committing someone else. Members, whose catalog role has tasks:complete but not tasks:assign, receive 403 on the Jobs-tab Claim button. Callers who hold tasks:assign pass the check and the RPC commits that id, so officers can still claim. Self-leave of an organizer and GET /api/attendance/summary?member_id=<own uuid> 403 for anyone without the officer permission, even though the id is theirs. Comparisons
- **Where:** `api/tasks/api/commitments.py:46-48 (commit_task)`, `api/tasks/api/commitments.py:73-75 (uncommit_task)`, `api/events/services/events.py:700-706 (add_organizer)`, `api/events/services/events.py:732-741 (remove_organizer)`
- **How it goes wrong:** 1. Member without tasks:assign opens Jobs and clicks Claim. 2. POST /api/tasks/{task_id}/commit {"member_id":"<their uuid string>"} with their bearer token. 3. 403 Missing permission: tasks:assign. 4. The same member claims from an event card, which omits member_id, and gets 200. 5. GET /api/attendance/summary?member_id=<same uuid string> → 403 You may only view your own attendance summary.
- **Why it matters / blast radius:** The Jobs tab tells a member they claimed a job (optimistic state in handleClaimTask) and the server rejects it. The check fails closed, so it is not an IDOR, but it disables the member self-service path the route documents. — Every member self-claim from TasksModule. API clients that pass their own id into commit, uncommit, add/remove organizer, or attendance summary. Officers with tasks:assign are unaffected for commit.
- **Tests catch it?** no. Frontend claim tests stub onClaimTask. No backend test asserts commit with member_id equal to the string form of the caller.
- **Fix:** Compare with str() on both sides in commitments.py, events.py add/remove organizer, and summary.py, matching balances.py. Add one test that a member can commit when body.member_id is str(user id). · scope: **surgical**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Codex: Raw UUID-versus-string comparisons reject legitimate self-se
- **Lead note:** UUID-vs-str comparisons; fails closed for self-service paths.

<a id="f-027"></a>
#### F-027 · 🟠 P1 · confirmed · treasury adjustments
**Any officer can post a sub-$500 adjustment against their own member id, and it takes effect immediately**

- **What happens:** Below $500, one holder of treasury:adjustment:create creates an active adjustment. The subject may be the caller. Each call is audited and idempotent only if the client sends an Idempotency-Key. A second call with a new key posts another adjustment. Chapter-level (member_id null) adjustments move chapter cash, not a member balance. Over $500 the row stays pending until a different officer approves.
- **Where:** `api/treasury/services/adjustments.py:13-44 (LARGE_ADJUSTMENT_THRESHOLD_CENTS, create_adjustment)`, `api/treasury/api/adjustments.py:22-45 (AdjustmentCreate)`, `migrations/0080_treasury_tenant_guards.sql:214-234 (tr_create_adjustment)`, `migrations/0147_authority_one_gate.sql:51-70 (officer role_permissions)`
- **How it goes wrong:** 1. Any member with the officer role (0147 gives that role adjustment:create) POSTs /api/treasury/adjustments {member_id: <own id>, kind: 'dues_forgiveness', delta_cents: -49999, reason: 'correction'} with no Idempotency-Key. 2. RPC inserts finance_adjustments status=active and big_ledger ADJUSTMENT_CREATED -49999. 3. recompute_member runs. current_balance drops by $499.99. 4. Repeat with a new request. No second officer is involved until a single call reaches $500.
- **Why it matters / blast radius:** This is credit with no cash and no second person. Self-verify of a payment (already reported) at least pretends money arrived. A dues_forgiveness of -49999 cents reduces the caller's own outstanding immediately, and repeating it clears any balance. The two-officer test fixture uses officer_id equal  — Every officer in every chapter, up to $499.99 per request, unlimited requests. Audited, not blocked.
- **Tests catch it?** no. tests/treasury/test_chunkE_adjustments_refunds.py::test_over_threshold_adjustment_requires_second_signoff and test_over_threshold_adjustment_cannot_be_self_approved cover only the pending path. They create the row with officer_id=member_id and do
- **Fix:** Reject p_actor_id = p_member_id in tr_create_adjustment, or require the second-officer path for any negative delta that credits the actor. Stop granting treasury:adjustment:create to the blanket officer role; leave it on treasurer. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** lead session: Money approvers can verify their own payment submissions
- **Lead note:** Officers can credit themselves: adjustments (confirmed) and self-verify (lead, likely).

<a id="f-028"></a>
#### F-028 · 🟠 P1 · confirmed · treasury balance cache / announcements
**Treasurer dashboard, balance CSV, and 'members with balance' SMS read member_finance_accounts without recomputing it**

- **What happens:** get_member_balance and the member dashboard recompute one member, then read the cache. The chapter dashboard, the member-balances export, the SMS blast audience, and the announcement feed do not. Money RPCs commit, then Python recomputes. A writer that skips recompute leaves the cache missing or stale until some other call happens to recompute that member.
- **Where:** `api/treasury/services/reports.py:136-148 (dashboard_summary)`, `api/treasury/services/reports.py:354-366 (period_report_csv member_balances)`, `api/announcements/services/sms.py:127-139 (resolve_recipients)`, `api/announcements/services/announcements.py:132-141 (audiences_for_viewer)`
- **How it goes wrong:** 1. Officer POSTs /api/fines/process-event/{event_id}. process_event_fines inserts invoices through tr_create_invoice and returns. No member_finance_accounts upsert. 2. GET /api/treasury/dashboard sums the old cache; the new fines are absent from total_outstanding_cents. 3. Officer sends an announcement with audience members_with_balance. resolve_recipients never loads those members. 4. Same window if any money RPC commits and the following recompute_member raises: the HTTP call 500s, the invoice or payment is already durable, and a client that does not retry leaves the dashboard wrong. Opening that one member's balance heals only that row.
- **Why it matters / blast radius:** The number the treasurer sees as 'total outstanding' and the set of people who receive a balance blast are not the operational tables. After the legacy fine run, new fine invoices exist and standing (which reads invoices) can see them, but the dashboard outstanding sum and the SMS audience omit ever — Treasurer dashboard, CSV export of member balances, SMS and in-app audiences. One chapter. Not the per-member balance endpoint.
- **Tests catch it?** no. Treasury tests that stub recompute_member_balance (test_v1_allocation.py autouse fixture) never assert dashboard_summary against a dirty cache. No announcement test found that issues an invoice and checks the balance audience without a prior reco
- **Fix:** Have dashboard_summary, the CSV export, and the balance audience sum BalanceEngine figures (or call recompute_all first). Fold the cache upsert into the money RPCs so it commits with the invoice or payment. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Cursor/Grok: Approving an excuse voids the fine inside plpgsql and never 
- **Lead note:** member_finance_accounts read stale by reports; excuse approval never refreshes it.

<a id="f-029"></a>
#### F-029 · 🟠 P1 · confirmed · treasury payments / allocations
**Invoice coverage is stored two ways, and reallocating a payment that still has verified_payments.invoice_id marks a second invoice paid**

- **What happens:** A v2 verification attributes money only through payment_allocations. A legacy verification, and every paid fine migrated by 0012, also stores coverage on verified_payments.invoice_id. Reallocating one of those payments adds allocations without removing the direct column, so tr_invoice_remaining_cents subtracts the same cents twice and tr_refresh_invoice_status can mark both the original invoice and the new target paid. Separately, legacy verify does not call tr_refresh_invoice_status: it ignores
- **Where:** `migrations/0031_treasury_payment_rpcs.sql:54-97 (tr_verify_payment)`, `migrations/0124_treasury_v1_allocations.sql:79-120 (tr_invoice_remaining_cents, tr_refresh_invoice_status)`, `migrations/0124_treasury_v1_allocations.sql:167-218 (tr_verify_payment_v2)`, `migrations/0124_treasury_v1_allocations.sql:297-346 (tr_reallocate_payment)`
- **How it goes wrong:** 1. A paid fine was migrated by 0012, or an officer POSTs /api/treasury/payments/submissions/{id}/verify (not verify-v1) on an invoice-targeted submission. verified_payments.invoice_id = invoice A, A.status = paid. 2. Treasurer POSTs /api/treasury/payments/{vp}/reallocate with allocations [{invoice_id: B, amount_cents: A's amount}] and a reason. 3. No prior allocation rows exist, so nothing is reversed. A new allocation lands on B. remaining(A) = amount - direct - 0 = 0 (stays paid). remaining(B) = amount - 0 - allocation = 0 (becomes paid). 4. owed includes A and B; paid includes the money once. outstanding equals one invoice, but neither invoice is open. 5.
- **Why it matters / blast radius:** BalanceEngine still counts every non-cancelled invoice in owed and every verified payment in paid, so the member's outstanding number stays honest. Invoice status does not. Open-invoice lists, fine totals, oldest-first allocation, and the SPA pay form all key off status. One historical or legacy-ver — Any chapter with a 0012 paid-fine row, or any client that still calls the legacy verify route. The current SPA calls verify-v1 only, so it does not create new invoice_id payments, but reallocate of mi
- **Tests catch it?** no. tests/treasury/test_v1_allocation.py reallocates only v2 payments (invoice_id NULL) and expects the original invoice to return to unpaid. tests/treasury/test_chunkC_payments.py exercises tr_verify_payment in isolation and does not void-then-verif
- **Fix:** Make coverage one mechanism: tr_reallocate_payment and tr_verify_payment should refuse or null invoice_id before allocating, and every status write should go through tr_refresh_invoice_status, which already leaves cancelled rows alone. Remove or 410 the legacy verify route. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1 · **also reported as:** Cursor/Grok: The unversioned payment verify route still runs tr_verify_pa
- **Lead note:** Legacy tr_verify_payment route overwrites invoice status computed by v2 allocations.

<a id="f-030"></a>
#### F-030 · 🟠 P1 · confirmed · treasury refunds
**A refund raises what the member owes and does not reopen an invoice, and the SPA can only pay an open invoice**

- **What happens:** The signs match: a refund reduces chapter cash and increases the member's net position back toward owing (it undoes paid, it does not also delete the payment). The invoice that the payment covered stays paid, because coverage lives in allocations / invoice_id and the refund RPC does not touch them. outstanding becomes positive with zero open invoices when that was the member's only invoice. Officer role includes treasury:refund:create (0147), so this is not treasurer-only.
- **Where:** `migrations/0052_treasury_refund_rpc.sql:40-61 (tr_issue_refund)`, `api/treasury/core/balance.py:96-102 (_member_figures)`, `api/treasury/core/balance.py:23-46 (chapter_balance)`, `api/treasury/services/refunds.py:16-48 (issue_refund)`
- **How it goes wrong:** 1. Member pays a $100 invoice; verify-v1 marks it paid; outstanding 0. 2. Officer POSTs /api/treasury/refunds {verified_payment_id, amount_cents: 10000, reason}. 3. refunds row active, ledger -10000, invoice still paid. current = 10000 owed - 10000 paid + 10000 refund = 10000. 4. Member opens Finance. open_invoices is empty (status filter unpaid/partially_paid). The pay form never renders a target. 5. Chapter cash is down $100. The receivable exists only as a balance figure.
- **Why it matters / blast radius:** The balance number is right and the invoice list is not. The member owes again, the chapter has less cash, and the only pay control in the product needs an open invoice. POST /api/treasury/payments/balance-submissions would accept a payment against the overall balance, but the SPA never calls it. Un — Any refund of a payment that fully covered the member's open invoices. Partial refunds leave the same gap for the refunded slice.
- **Tests catch it?** partial. tests/treasury/test_chunkE_adjustments_refunds.py asserts the cap, the negative ledger row, and the balance formula. It does not assert invoice status after a refund, and nothing in greekos asserts a way to pay a positive outstanding with no
- **Fix:** On refund, append allocation reversals up to the refunded amount and let tr_refresh_invoice_status reopen the invoice, or create a replacement invoice for the refunded cents inside the same RPC. Expose balance submissions in the pay UI when outstanding > 0 and open invoices are empty. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1

<a id="f-031"></a>
#### F-031 · 🟠 P1 · confirmed · treasury schema / balance engine
**The tables balances are computed from can be updated in place; the append-only ledger is not what members owe**

- **What happens:** Application routes do not .update() these tables; money routes go through RPCs. The connection is the table owner, which bypasses RLS, and the query builder will run an UPDATE if any caller asks. Changing verified_payments.amount_cents changes outstanding and chapter cash on the next recompute, while the receipt and the PAYMENT_RECEIVED row keep the old amount. Changing finance_adjustments.delta_cents changes the member balance without a new ledger row. Rebuild would report drift after the fact.
- **Where:** `api/treasury/core/balance.py:23-102 (chapter_balance, _member_figures)`, `migrations/0010_treasury_receivables_tables.sql:57-76 (verified_payments)`, `migrations/0050_treasury_adjustments_refunds_tables.sql:12-65 (finance_adjustments, refunds triggers)`, `migrations/0030_treasury_receipts.sql:22-31 (receipts_no_update, receipts_no_delete)`
- **How it goes wrong:** 1. Owner session: UPDATE verified_payments SET amount_cents = amount_cents + 100000 WHERE id = <payment>. 2. Receipt row still shows the original amount (update trigger rejects a matching receipt edit). PAYMENT_RECEIVED stays at the original amount. 3. Next get_member_balance recomputes from verified_payments and drops the member's outstanding by $1000, and chapter_balance rises by $1000. 4. POST /api/treasury/rebuild reports a PAYMENT_RECEIVED count mismatch and does not change big_ledger. The new balance remains.
- **Why it matters / blast radius:** The append-only story is true for the shadow log and false for the tables that define what a member owes. One UPDATE from the owner role, a future service bug, or a Supabase SQL editor session rewrites balances with no audit row. Invalidating a ledger row (the one mutation the trigger allows) is als — All chapters, any path that can issue SQL as the pooler role. No current route does this. The gap is the integrity model, not a live handler.
- **Tests catch it?** partial. tests/treasury/test_chunk0_foundations.py asserts ledger and audit immutability. tests/treasury/test_chunkG_rebuild_hardening.py asserts rebuild reports drift and does not rewrite the ledger. No test asserts that verified_payments.amount_cen
- **Fix:** Before-update triggers on verified_payments, finance_adjustments, refunds, and unpaid_invoices that allow only the column transitions the RPCs actually perform (invoice status, adjustment pending→active, expense active→invalidated, submission pending→approved/rejected). Point balance reads at those guarded rows knowing the amounts are frozen. Audit the ledger active→invalidated transition inside t · scope: **medium**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P1


### 🟡 P2 — 27 findings

| ID | Subsystem | One line | Confidence | Fix size |
|---|---|---|---|---|
| [F-033](#f-033) | RBAC | Authorization repeatedly reloads the same role and permission set within one request | confirmed | medium |
| [F-034](#f-034) | announcements/outbox | Every in-app announcement creates a guaranteed failed delivery row | confirmed | small |
| [F-036](#f-036) | attendance | Unauthenticated phone check-in lets anyone with the live code check in any member | confirmed | small |
| [F-038](#f-038) | backup and disaster re | Production backup capability and recovery time remain unverified | likely | architectural |
| [F-039](#f-039) | database client | The PostgREST compatibility parser silently drops unsupported nested joins | confirmed | medium |
| [F-009](#f-009) | db | Test suite runs entirely as superuser, bypassing RLS | confirmed | architectural |
| [F-040](#f-040) | developer tooling/depe | Local dependency bootstrap validates only one import, so tests run against stale versions | confirmed | small |
| [F-041](#f-041) | documentation | Docs describe architecture that does not exist | confirmed | small |
| [F-042](#f-042) | event security | Concurrent security assignment can create duplicate active shifts for one member/event | confirmed | medium |
| [F-043](#f-043) | events notifications | Event-role dedup keys suppress notifications after a real remove/reassign cycle | confirmed | small |
| [F-044](#f-044) | frontend application d | SPA startup issues 15 + 3N requests and then serializes them through synchronous backend I | confirmed | architectural |
| [F-046](#f-046) | health monitoring | The public health endpoint reports HTTP 200 even when its database check fails | confirmed | surgical |
| [F-047](#f-047) | initiatives | Concurrent chair removals can leave an initiative with zero chairs | confirmed | small |
| [F-048](#f-048) | instrumentation/storag | Any authenticated member can permanently append unbounded usage data | confirmed | medium |
| [F-016](#f-016) | migrations / prod | Filling in the prod project ref and running migrate would apply the LocalDev history on to | likely | medium |
| [F-018](#f-018) | notifications/cron | Outbox drain can exhaust attempts without a real delivery attempt under serverless timeout | likely | small |
| [F-050](#f-050) | notifications/operator | Manual retry is non-atomic and never reconciles its parent send log | confirmed | small |
| [F-020](#f-020) | ops/auth | set_officer_password.py writes any DATABASE_URL and does not revoke sessions | confirmed | surgical |
| [F-051](#f-051) | outbox operations | There is no durable cron heartbeat, backlog alarm, or last-success signal | confirmed | medium |
| [F-053](#f-053) | tasks / operations | The mounted operations template engine is an orphaned second task system | confirmed | architectural |
| [F-054](#f-054) | tasks security and ini | Assignment RPCs accept inactive or invited members as workers, chairs, and security target | confirmed | medium |
| [F-056](#f-056) | treasury dashboard | Member treasury dashboard has a 2N invoice query loop on top of cache recomputation | confirmed | small |
| [F-057](#f-057) | treasury fines | Manual fine issuance expands to approximately eight committed database operations per memb | confirmed | medium |
| [F-058](#f-058) | treasury rebuild | Rebuild can call the ledger clean when a missing payment row and an extra payment row shar | confirmed | small |
| [F-032](#f-032) | treasury verify / gree | The payment the member submits against one invoice is applied oldest-first to a different  | confirmed | small |
| [F-059](#f-059) | treasury/fines | Legacy POST /api/fines/process-event bypasses V1 fine rules | confirmed | small |
| [F-060](#f-060) | treasury/fines, tasks | Naive event times treated as UTC in fine and task timing | confirmed | small |

<details><summary>▸ P2 cards (27)</summary>

<a id="f-033"></a>
#### F-033 · 🟡 P2 · confirmed · RBAC
**Authorization repeatedly reloads the same role and permission set within one request**

- **What happens:** There is no request-scoped permission cache. A simple roster read costs one auth query, two permission queries, and one roster query. `/me/permissions` costs four queries including auth. Branches that check two alternative permissions can spend four permission queries for the same actor.
- **Where:** `api/rbac/services/permissions.py:46-65 (get_member_permissions and has_permission)`, `api/rbac/db/repositories/member_roles.py:6-26 (permission queries)`, `api/rbac/auth.py:27-37 (require_permission)`, `api/rbac/api/roles.py:28-36 (get_my_permissions)`
- **How it goes wrong:** 1. The SPA launches its startup requests. 2. Each independently loads the member row and permissions. 3. A treasury or outbox endpoint checks more than one capability and repeats both RBAC reads. 4. The per-instance connection pool and event loop spend much of startup repeating immutable request-local data.
- **Why it matters / blast radius:** Permission resolution is on nearly every startup endpoint, amplifying the 15 + 3N frontend fan-out and consuming connections without changing results during a request. — Nearly every authenticated API request; greatest during SPA startup and officer workflows.
- **Tests catch it?** partial — `tests/rbac/test_permissions_service.py` validates permission semantics, but no test asserts query counts or reuse. Route tests do not detect repeated resolution.
- **Fix:** Resolve an immutable `ActorContext` once per request containing the member, role keys, and permission set. Make `require_permission` and inline ownership checks consume that context; have `/me/permissions` return the already-resolved roles and keys. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-034"></a>
#### F-034 · 🟡 P2 · confirmed · announcements/outbox
**Every in-app announcement creates a guaranteed failed delivery row**

- **What happens:** Posting an announcement succeeds in the feed, but its companion outbox row always fails. Retrying it repeats the same deterministic failure. The advertised delivery-time audience resolution never occurs.
- **Where:** `migrations/0086_announcements_tables_rpcs.sql:76-89 (an_send_announcement)`, `api/cron/services/outbox_drain.py:252-270 (_deliver_row)`, `api/announcements/services/announcements.py:117-172 (audiences_for_viewer, list_announcements)`
- **How it goes wrong:** 1. An officer sends an announcement to `officers`. 2. The RPC commits the feed post and a recipient-less outbox row. 3. Cron claims the row. 4. The drain marks it failed without resolving officers. 5. The outbox UI shows a failure; Retry can never succeed.
- **Why it matters / blast radius:** Operators accumulate false failures and cannot distinguish expected feed markers from genuine notification outages. Officers-only audience resolution works for the feed and manual SMS, but not for this automatic email event. — One permanent failed row for every sent announcement, for every audience type.
- **Tests catch it?** yes, but codifies the defect — tests/cron/test_drain_outbox.py::test_row_without_member_is_failed_not_stranded expects this failure. Announcement feed audience tests cover the separate in-app path.
- **Fix:** Either remove `ANNOUNCEMENT_PUBLISHED` from the delivery outbox and treat the announcement table as the feed, or fan out per-member email rows atomically at send time. Do not represent an intentional non-delivery as failed. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-036"></a>
#### F-036 · 🟡 P2 · confirmed · attendance
**Unauthenticated phone check-in lets anyone with the live code check in any member**

- **What happens:** Attendance can be forged for absent members; phone enumeration
- **Where:** `api/attendance/api/attendance.py:74-128 (checkin_phone)`, `api/events/api/events.py:224-285 (checkin-link read has no permission gate)`
- **How it goes wrong:** 1. Member reads code via GET /api/events/{id}/checkin-link. 2. POSTs a friend's phone. 3. Friend marked present.
- **Why it matters / blast radius:** Standing and fines computed from forged attendance — Attendance integrity
- **Tests catch it?** No
- **Fix:** Tie phone check-in to a session-bound token or require login; rate limit; gate the link read · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P2 · **also reported as:** Cursor/Grok: Phone check-in marks whichever member row comes back first w; Cursor/Grok: Phone check-in picks an arbitrary member when a chapter has 
- **Lead note:** Phone check-in: unauthenticated + arbitrary member on duplicate phones.

<a id="f-038"></a>
#### F-038 · 🟡 P2 · likely · backup and disaster recovery
**Production backup capability and recovery time remain unverified**

- **What happens:** The repository provides commands but no evidence that a usable production backup exists, how recent it is, or how long restoration takes.
- **Where:** `docs/ops-runbook.md:63-76 (backup assumptions)`, `docs/ops-runbook.md:78-111 (manual dump and restore drill)`, `docs/research/prod-ops-readiness.md:164-183 (restore mechanics)`
- **How it goes wrong:** 1. A migration or operator corrupts production data. 2. The team opens the runbook. 3. Supabase retention/PITR status is still unknown and no recent independent dump can be identified. 4. The never-tested restore procedure fails or takes an unknown duration. 5. Data is lost or the platform remains unavailable.
- **Why it matters / blast radius:** GreekOS stores real roster and financial data, with multiple append-only tables and forward-only migrations. Recovery capability discovered only after corruption is not a recovery plan. — All production chapters and historical financial/audit records.
- **Tests catch it?** no — external backup state and restoration are not tested by the repository.
- **Fix:** Verify and record the live Supabase plan now, automate encrypted off-provider dumps with freshness alerts, and complete a timed restore drill. Record RPO/RTO and the last successful restore artifact. · scope: **architectural**
- **Found by:** Codex · **verified by:** lead only
- **Lead note:** Not a code finding; lead downgrades to P2/likely, no refute run.

<a id="f-039"></a>
#### F-039 · 🟡 P2 · confirmed · database client
**The PostgREST compatibility parser silently drops unsupported nested joins**

- **What happens:** A developer can write a syntactically valid Supabase-style nested select for an unregistered relation and receive base rows with the nested field silently absent. The shim's missing joins also force manual stitching and extra queries in services.
- **Where:** `api/platform/postgres.py:30-57 (FK_MAP and JOIN_STAR_COLUMNS)`, `api/platform/postgres.py:190-215 (_parse_select)`, `api/platform/postgres.py:217-275 (_exec_select)`, `api/treasury/api/fines_legacy.py:77-101 (_present_fines)`
- **How it goes wrong:** 1. A new route selects `unpaid_invoices(*, members(name))`. 2. `_parse_select` strips `members(name)` because that base-table mapping is absent. 3. The query succeeds and returns invoice rows without `members`. 4. Response code treats missing nested data as an empty/default state rather than exposing the unsupported query.
- **Why it matters / blast radius:** The abstraction looks general but has a small hard-coded relationship catalog. Silent degradation is more dangerous than an unsupported-operation error and encourages per-domain workarounds. — Any new or refactored query using PostgREST nested-select syntax outside the six hard-coded tables; maintenance cost spans all domains using `sb`.
- **Tests catch it?** no — no query-builder test was found asserting that an unsupported nested join raises. Existing callers work around missing mappings manually.
- **Fix:** Fail fast on every unrecognized nested relation. Longer term, replace the emulation with explicit SQL/repository queries for complex reads while retaining a small typed CRUD helper only where it is genuinely simpler. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-009"></a>
#### F-009 · 🟡 P2 · confirmed · db
**Test suite runs entirely as superuser, bypassing RLS**

- **What happens:** The test database connects using the postgres role (TEST_DATABASE_URL), which inherently bypasses RLS. Consequently, no tests exercise RLS enforcement.
- **Where:** `tests/treasury/conftest.py:163-177`
- **How it goes wrong:** If a developer drops a chapter_id filter in python, the tests will not fail because the DB connection bypasses RLS.
- **Why it matters / blast radius:** Tenant isolation relies completely on python query filters. Because the test suite bypasses RLS, it cannot verify whether RLS policies are actually correct or whether they would catch a missing python filter. — Cross-tenant data leakage.
- **Tests catch it?** no
- **Fix:** Use a non-superuser role for the test database connection or mock the PostgREST claims to enforce RLS in tests. · scope: **architectural**
- **Found by:** Gemini Pro · **verified by:** refute@cursor: downgraded P2
- **Lead note:** Refuter (Grok) downgraded P1→P2: the suite cannot see RLS, but RLS is not the runtime boundary. Lead agrees.

<a id="f-040"></a>
#### F-040 · 🟡 P2 · confirmed · developer tooling/dependencies
**Local dependency bootstrap validates only one import, so tests run against stale versions**

- **What happens:** Once any FastAPI is installed, Dependabot/manifest changes do not update the developer environment. Local validation and CI/deployment exercise different interpreter and library versions.
- **Where:** `../local-dev-scripts/scripts/local-dev.sh:202-208 (Python dependency check)`, `requirements.txt:1-11 (pinned environment)`, `../.github/workflows/ci.yml:49-56 (CI installation)`
- **How it goes wrong:** 1. Dependabot raises a pinned dependency. 2. A developer runs the local bootstrap. 3. `import fastapi` succeeds, so no installation occurs. 4. Tests pass against the old stack. 5. CI installs the new pins and fails or behaves differently.
- **Why it matters / blast radius:** Compatibility failures can appear only after push or deployment, while local green tests provide false confidence. This is amplified by the lack of Python lint/type gates. — All backend development and local verification; deployment reproducibility.
- **Tests catch it?** no — no tooling test checks installed versions against requirements.
- **Fix:** Use a project virtual environment and install/sync from a hashed lock or requirements whenever its digest changes. Pin the supported Python version and expose a `doctor` command that compares all installed versions. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-041"></a>
#### F-041 · 🟡 P2 · confirmed · documentation
**Docs describe architecture that does not exist**

- **What happens:** Agents and humans are steered to non-existent structure
- **Where:** `LocalDev/CLAUDE.md (frontend section)`, `CLAUDE.md (root)`, `docs/adr/0002`
- **How it goes wrong:** n/a
- **Why it matters / blast radius:** Every new agent session starts wrong — All contributors
- **Tests catch it?** No
- **Fix:** Rewrite the frontend section from the real tree; add a doc check to CI · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P2

<a id="f-042"></a>
#### F-042 · 🟡 P2 · confirmed · event security
**Concurrent security assignment can create duplicate active shifts for one member/event**

- **What happens:** Sequential duplicate assignments are rejected, but two concurrent transactions can both pass the pre-check and each create a distinct security task with an active commitment for the same member and event.
- **Where:** `migrations/0145_security_swaps_v1.sql:207-294 (ev_assign_security)`, `migrations/0145_security_swaps_v1.sql:30-40 (security task constraints)`, `tests/events/test_security.py:143-158 (test_assign_same_member_twice_rejected_but_other_event_ok)`
- **How it goes wrong:** 1. Two supervisors assign the same member to security on the same event concurrently. 2. Both transactions query before either inserts. 3. Both see no assignment. 4. Each creates a security task, commitment, log, audit row, and outbox notification.
- **Why it matters / blast radius:** The same member can appear twice in security staffing, receive duplicate notifications, and accrue distorted prior-security-shift scoring after approval. — Security rosters, notification outbox, commitment history, and prior-security-shift engagement scoring.
- **Tests catch it?** No. `tests/events/test_security.py` tests two sequential calls only.
- **Fix:** Serialize security assignment on the event or member/event advisory key and recheck under the lock. Prefer a schema representation that permits a partial unique constraint directly. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: upgraded P1
- **Lead note:** Refuter (Gemini) upgraded to P1 (READ COMMITTED double insert). Lead keeps P2: needs two simultaneous assignments of one member. Disputed.

<a id="f-043"></a>
#### F-043 · 🟡 P2 · confirmed · events notifications
**Event-role dedup keys suppress notifications after a real remove/reassign cycle**

- **What happens:** Only the first assignment of a member to a given event/role produces email. A later legitimate reassignment silently collides with historical delivery.
- **Where:** `api/events/notifications.py:81-98 (notify_role_assigned)`, `api/events/services/events.py:625-689 (add_supervisor, remove_supervisor)`, `api/events/services/events.py:692-754 (add_organizer, remove_organizer)`
- **How it goes wrong:** 1. An officer assigns member M as organizer; one email is queued. 2. M is removed. 3. Days later, an officer assigns M again. 4. The assignment RPC succeeds. 5. The notification insert sees the old dedup key and returns no row, so M receives no second assignment notice.
- **Why it matters / blast radius:** Members can be re-added to event responsibility without receiving the notification that tells them they are responsible. — Organizer and supervisor reassignment notifications.
- **Tests catch it?** no — tests/events/test_event_emails.py verifies one assignment and separate organizer/supervisor keys, but does not exercise remove then re-add.
- **Fix:** Deduplicate by assignment record/cycle ID or include the assignment audit/RPC result ID. Preserve idempotency for retries of one assignment while allowing a later distinct assignment. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-044"></a>
#### F-044 · 🟡 P2 · confirmed · frontend application data loading
**SPA startup issues 15 + 3N requests and then serializes them through synchronous backend I/O**

- **What happens:** A chapter with 20 upcoming events makes 75 startup HTTP requests. Payloads duplicate the event list in 20 event-detail responses and independently transfer all roster, standing, scores, tasks, excuses, fines, announcements, recruits, initiatives, and contribution rows.
- **Where:** `greekos/src/hooks/useAppData.ts:126-165 (initial load phases)`, `greekos/src/hooks/useAppData.ts:167-193 (per-upcoming-event requests)`, `greekos/src/hooks/useAppData.ts:104-109 (refetchJobsRef)`, `api/platform/postgres.py:169-186 (blocking QueryBuilder.execute)`
- **How it goes wrong:** 1. A 100-member chapter has 20 upcoming events. 2. An officer opens the app. 3. The browser dispatches 75 requests. 4. Each request independently authenticates and many independently resolve permissions. 5. The backend serializes substantial portions through blocking calls, causing slow startup or transient failures; failed event enrichments silently leave partial cards.
- **Why it matters / blast radius:** Although the browser launches batches concurrently, a single serverless instance cannot benefit fully because the handlers perform blocking I/O. Startup latency and database work grow with upcoming events, the most common active-period workload. — Every authenticated SPA load; officers incur the heaviest payload because their optional endpoints succeed rather than cheaply 403.
- **Tests catch it?** no — frontend unit tests cover pure adapters/helpers, not an integration-level request budget or duplicate-fetch assertion.
- **Fix:** Create one bootstrap endpoint returning identity, permissions, roster-derived data, and bounded domain summaries. Include security/detail/link summary fields in the event list or add one bulk event-enrichment endpoint. Add client caching/deduplication and a request-count integration test. · scope: **architectural**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-046"></a>
#### F-046 · 🟡 P2 · confirmed · health monitoring
**The public health endpoint reports HTTP 200 even when its database check fails**

- **What happens:** Payload-aware `check_prod_status.py` detects the outage, but ordinary HTTP-status uptime checks treat a database-dead application as available.
- **Where:** `api/health_checks.py:30-52 (build_health_payload)`, `api/index.py:214-216 (health)`, `docs/research/prod-ops-readiness.md:102-107 (uptime monitor recommendation)`
- **How it goes wrong:** 1. Supabase becomes unreachable. 2. `/api/health` exhausts its retries. 3. FastAPI serializes the error payload with HTTP 200. 4. A status-only monitor records success and does not page anyone.
- **Why it matters / blast radius:** The documented low-cost monitoring plan can miss pool exhaustion, paused database, authentication failure, or a dead database while user requests fail. — Production availability detection for the entire backend.
- **Tests catch it?** partial — tests/test_check_prod_status.py validates the custom script’s payload parsing, but no route test requires HTTP 503 on database failure.
- **Fix:** Return 503 when required checks fail and keep the structured body. Document whether the endpoint is liveness or readiness, and configure monitoring to assert both status code and payload. · scope: **surgical**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-047"></a>
#### F-047 · 🟡 P2 · confirmed · initiatives
**Concurrent chair removals can leave an initiative with zero chairs**

- **What happens:** The last-chair check works sequentially but is vulnerable to write skew. Two chairs can remove one another concurrently and both commits can succeed, leaving no actor authorized by chair membership to manage the initiative.
- **Where:** `migrations/0144_initiatives_v1.sql:274-334 (in_remove_chair)`, `migrations/0144_initiatives_v1.sql:36-45 (initiative_chairs schema)`, `tests/initiatives/test_initiatives_rpcs.py:195-230 (chair removal tests)`
- **How it goes wrong:** 1. Initiative has chairs A and B. 2. A requests removal of B while B requests removal of A. 3. Each locks a different target row and counts two visible chairs. 4. Both delete. 5. The initiative has zero chairs.
- **Why it matters / blast radius:** An initiative can become administratively orphaned, blocking normal updates and chair management. — Any initiative with exactly two chairs, including its jobs and approval authority.
- **Tests catch it?** No. `tests/initiatives/test_initiatives_rpcs.py` covers sequential co-chair removal and sequential rejection of removing the sole chair.
- **Fix:** Lock the parent initiative row before authorization/count/removal so chair mutations serialize. Recheck actor membership and remaining count after acquiring the common lock. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-048"></a>
#### F-048 · 🟡 P2 · confirmed · instrumentation/storage
**Any authenticated member can permanently append unbounded usage data**

- **What happens:** A plain member can submit an unlimited number of roughly 8 KB immutable rows with attacker-chosen event names and metadata. The endpoint always returns `{'ok': true}` even if tracking fails.
- **Where:** `api/instrumentation/api/usage.py:14-26 (track_usage)`, `api/instrumentation/api/schemas.py:8-10 (UsageTrack)`, `api/instrumentation/services/usage.py:19-50 (track)`, `migrations/0140_usage_events.sql:6-12 (usage_events)`
- **How it goes wrong:** 1. A member authenticates normally. 2. A script repeatedly POSTs 8 KB metadata to `/api/usage/track`. 3. Each request appends a row. 4. Operators cannot delete or compact rows because the trigger rejects deletion. 5. Storage and index size grow until service or billing impact occurs.
- **Why it matters / blast radius:** A low-privilege account can drive database storage/cost and degrade queries until the chapter or database is deleted. Arbitrary metadata also creates an uncontrolled PII retention surface. — The shared database and every chapter using it; usage summaries also become increasingly expensive.
- **Tests catch it?** partial — tests/calendar_view/test_usage_instrumentation.py verifies per-row truncation and explicitly verifies UPDATE/DELETE rejection, but has no rate-limit, quota, retention, or abuse test.
- **Fix:** Remove the public generic tracker or restrict it to a closed event catalog. Add per-member rate limits, chapter quotas, metadata allowlists, and a privileged retention/pruning mechanism instead of universal immutability. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: upgraded P1
- **Lead note:** Lead downgrades to P2 (abuse/perf, not correctness). Refuter (Gemini) upgraded to P1 and added a real fact: the usage_events immutability trigger (0140:28-40) also blocks cascaded chapter/member deletes. Lead keeps P2: no delete feature exists yet.

<a id="f-016"></a>
#### F-016 · 🟡 P2 · likely · migrations / prod
**Filling in the prod project ref and running migrate would apply the LocalDev history on top of a database that only recorded Prod's two filenames**

- **What happens:** migrate_db.py --prod exits before connecting usefully, because the guard is empty. If a human pastes the prod ref, as the comment in db_guard.py instructs, and schema_migrations on that database contains 0001_initial_schema.sql and 0002_add_password_hash.sql, then 0001 is skipped (same name) and the chapters-exists abort never runs. 0002_link_members_auth_id.sql runs (adds auth_id). 0004 runs and does not error on the existing password_hash column. Every later LocalDev file from 0003 and 0005 th
- **Where:** `scripts/migrate_db.py:95-98 (_applied_names)`, `scripts/migrate_db.py:146-179 (pending by filename, one transaction per file)`, `scripts/db_guard.py:31-38 (PROD_PROJECT_REFS empty)`, `migrations/0004_add_password_hash.sql:1-5`
- **How it goes wrong:** 1. Prod schema_migrations lists 0001_initial_schema.sql and 0002_add_password_hash.sql. Members and events rows exist. 2. Operator sets PROD_PROJECT_REFS and PROD_DATABASE_URL and runs scripts/migrate_db.py --prod --yes. 3. 0001 skipped. 0004 applies cleanly. 4. 0005+ create treasury tables and 0012 converts fines using round(amount * 100). 0149 copies unparseable phones to phone_unparsed and rewrites members.phone to E.164. 5. A later file that assumes a LocalDev-shaped 0001 fails mid-list; earlier files are already committed. There is no down migration.
- **Why it matters / blast radius:** The filename tracker treats 'prod has a password column' as 'prod has not had 0004', and IF NOT EXISTS means the collision does not stop the replay. The documented next step for production (put the ref in PROD_PROJECT_REFS and run the workflow) is the step that replays the whole treasury, RBAC, and  — The production database, if the guard is filled. Today the empty guard makes this inert. Demo and CI are unaffected because they already have the LocalDev names.
- **Tests catch it?** no. CI migrates a fresh Postgres with the LocalDev filenames. Nothing applies this tree to a database whose schema_migrations contains the Prod 0002 name.
- **Fix:** Before any prod migrate, record a checksum (or a generation id) and refuse to run when schema_migrations contains names that are not in this tree, or when 0001's applied body is only the MVP. Do not treat IF NOT EXISTS as a safe resume. Take a backup first; DATABASE.md points at the Supabase pooler and does not record a tested restore. · scope: **medium**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: downgraded P2 · **also reported as:** Codex: Filename-only migration tracking has already produced irreco; Cursor/Grok: 0147 and 0149 were edited after they had been applied, and s; Cursor/Grok: 0147 and 0149 were edited after they had been applied, and s
- **Lead note:** One root cause: migration history is not reproducible (filename tracking + edited-after-apply files). Refuter (Codex) downgraded: PROD_PROJECT_REFS guard blocks any prod migrate today. Lead agrees; the missing checksum/dry-run remains.

<a id="f-018"></a>
#### F-018 · 🟡 P2 · likely · notifications/cron
**Outbox drain can exhaust attempts without a real delivery attempt under serverless timeouts**

- **What happens:** Under load or slow SMTP, rows are marked failed after 5 claims even if never delivered
- **Where:** `api/cron/services/outbox_drain.py:284-315 (drain_outbox)`, `migrations/0155_outbox_claim_batch.sql (attempts incremented on claim)`, `vercel.json (no maxDuration)`
- **How it goes wrong:** 1. 100 emails queued. 2. Cron drains 10 s then is killed. 3. Rows stay 'sending' 15 min, reaper requeues, attempts+1. 4. Repeat ×5 → failed, never sent.
- **Why it matters / blast radius:** Silent loss of setup codes, invoices and reminders — All email/SMS delivery
- **Tests catch it?** Partial — tests/cron/test_drain_outbox.py covers claim/reaper but not timeouts
- **Fix:** Increment attempts on delivery attempt, bound batch by time budget, set maxDuration · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: downgraded P2
- **Lead note:** Refuter (Codex) downgraded: at the 300 s Vercel default the batch finishes; exhaustion needs five kills in a row. Lead agrees.

<a id="f-050"></a>
#### F-050 · 🟡 P2 · confirmed · notifications/operator retry
**Manual retry is non-atomic and never reconciles its parent send log**

- **What happens:** The requeue can commit while the audit insert fails, returning 500 even though the message is pending. After a successful retry, the child becomes sent but its parent send log remains failed.
- **Where:** `api/announcements/services/outbox.py:130-170 (retry_outbox_row)`, `api/cron/services/outbox_drain.py:284-315 (drain_outbox)`, `api/platform/postgres.py:169-186 (QueryBuilder.execute)`
- **How it goes wrong:** 1. An officer POSTs `/api/announcements/outbox/{row}/retry`. 2. The child update commits. 3. The audit insert fails. 4. The request returns 500, but cron sends the now-pending row. 5. The parent blast remains `failed`, and the required retry audit is absent.
- **Why it matters / blast radius:** An operator can unknowingly trigger an unaudited resend, retry the 500 and receive a confusing 409, and still see a failed parent after the member receives the message. — Every manually retried message; stale parent status specifically affects ANNOUNCEMENT_SMS and EVENT_NOTIFY.
- **Tests catch it?** partial — tests/announcements/test_outbox.py separately verifies requeue state and audit creation, but does not inject failure between them or drain the retried child and check parent reconciliation.
- **Fix:** Move requeue plus audit insertion into one tenant-guarded RPC. Recompute the parent status after each child terminal transition, or provide a reconciliation job/view derived from child states. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: upgraded P1
- **Lead note:** Refuter (Gemini) upgraded to P1. Lead keeps P2: operator retry path; stale parent send log is a display inconsistency. Disputed.

<a id="f-020"></a>
#### F-020 · 🟡 P2 · confirmed · ops/auth
**set_officer_password.py writes any DATABASE_URL and does not revoke sessions**

- **What happens:** Whoever can run the script against a database URL changes that officer's password. Existing JWTs stay valid until they expire (7 days) or something else bumps token_version. There is no typed project-ref confirmation. The WHERE clause also misses officers whose members.role is 'member' but who hold officer-equivalent catalog roles only in member_roles.
- **Where:** `scripts/set_officer_password.py:23-61 (main)`, `scripts/db_guard.py:89-103 (require_demo)`, `migrations/0148_auth_hardening.sql:119-132 (au_set_password)`
- **How it goes wrong:** 1. Operator (or anyone with a shell and a prod URL) runs DATABASE_URL=<target> python3 scripts/set_officer_password.py jake@chapter.edu and types a new password. 2. The row's password_hash changes; token_version stays put. 3. A JWT minted before the reset still passes get_current_user until exp or a later au_set_password/au_bump_token_version. 4. The same command against a non-demo URL succeeds; seed.py would have raised ProdGuardError.
- **Why it matters / blast radius:** This is the break-glass password tool and it skips both controls the app path has: the demo/prod URL guard, and session revocation. A stolen or old token keeps working after the operator thinks the password reset locked the account out. Pointing DATABASE_URL at the wrong project is not refused. — One officer row per invocation, plus every outstanding session for that member (up to 7 days). No chapter scoping beyond email uniqueness.
- **Tests catch it?** no. No test references set_officer_password.py.
- **Fix:** Call require_demo unless an explicit --prod confirmation matches db_guard, and update token_version in the same statement as password_hash (or call au_set_password). · scope: **surgical**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: downgraded P2 · **also reported as:** Codex: Break-glass password reset neither revokes existing sessions
- **Lead note:** Refuter (Codex) downgraded: offline credential-gated break-glass script, and the runbook does target prod on purpose. Session revocation gap stands.

<a id="f-051"></a>
#### F-051 · 🟡 P2 · confirmed · outbox operations
**There is no durable cron heartbeat, backlog alarm, or last-success signal**

- **What happens:** If Vercel stops invoking the cron, CRON_SECRET mismatches, or the route is absent in the actual deployment root, the API and database health check remain green while pending messages accumulate.
- **Where:** `vercel.json:16-20 (cron schedule)`, `api/cron/api/cron.py:38-45 (cron_drain_outbox)`, `api/cron/services/outbox_drain.py:306-315 (drain_outbox result/logging)`, `scripts/check_prod_status.py:21-47 (health evaluation)`
- **How it goes wrong:** 1. The deployed cron loses its secret or schedule. 2. No drain request reaches the app. 3. Health checks continue returning database `ok`. 4. Outbox rows remain pending. 5. The outage is discovered only when a member reports missing mail or an officer manually opens the outbox.
- **Why it matters / blast radius:** Setup/reset emails, treasury notices, job assignments, and other automatic notifications can stop indefinitely without producing an application error or operator signal. — All automatic email and queued SMS delivery for every chapter.
- **Tests catch it?** no — tests/cron/test_cron_auth.py verifies authentication and GET routing; tests/cron/test_drain_outbox.py verifies counts for an invoked worker. Neither detects a missing invocation or aged backlog.
- **Fix:** Persist each drain start/finish, duration, claimed count, oldest-pending age, and outcome. Add a monitor that alerts when no successful run occurs within two schedules or pending age crosses a threshold. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2
- **Lead note:** Lead downgrades to P2 (observability gap).

<a id="f-053"></a>
#### F-053 · 🟡 P2 · confirmed · tasks / operations
**The mounted operations template engine is an orphaned second task system**

- **What happens:** Calling apply-template mutates event flags and populates a checklist model that the Tasks UI and current job lifecycle do not consume. Its multi-row loop is non-transactional and bypasses the modern task audit/idempotency model.
- **Where:** `api/index.py:142-143 (operations router import)`, `api/index.py:199-203 (operations mount)`, `api/tasks/api/operations.py:16-32 (operations routes)`, `api/tasks/services/templates.py:16-59 (list_event_templates)`
- **How it goes wrong:** 1. A client discovers `/api/operations/templates`. 2. It applies a template to an event. 3. Several `event_roles`/`event_tasks` rows and legacy fine fields are committed. 4. The current Tasks UI continues to show no jobs. 5. Readiness remains `in_progress` because no API can update those rows.
- **Why it matters / blast radius:** It is active public surface, not harmless dead code. An officer or future agent can receive a successful response for work that is invisible in the product and cannot be completed through the API. — Events touched through the operations API and developers who mistake the 0003 engine for the current task architecture.
- **Tests catch it?** no — `tests/services_scaffold/test_route_registration.py` only asserts `/api/operations/templates` exists; no behavior, visibility, lifecycle, rollback, or frontend-consumption tests were found.
- **Fix:** Choose one task model. Prefer migrating any useful template concept to create modern `tasks` through a transactional `tk_*` RPC, then deprecate and remove the operations routes/tables after checking data. Until then, label the API deprecated and reject writes rather than creating invisible state. · scope: **architectural**
- **Found by:** Codex · **verified by:** refute@cursor: confirmed P2 · **also reported as:** Codex: The operations template engine writes a shadow task model in
- **Lead note:** Operations template engine: orphaned second task system.

<a id="f-054"></a>
#### F-054 · 🟡 P2 · confirmed · tasks security and initiatives
**Assignment RPCs accept inactive or invited members as workers, chairs, and security targets**

- **What happens:** An officer can commit an inactive/invited member to a job, assign them to security, target them in a security swap, or add them as an initiative chair. A target can become inactive after request and still be accepted into a swap.
- **Where:** `migrations/0145_security_swaps_v1.sql:237-265 (ev_assign_security)`, `migrations/0145_security_swaps_v1.sql:405-447 (ev_request_security_swap)`, `migrations/0145_security_swaps_v1.sql:519-561 (ev_accept_security_swap)`, `migrations/0145_security_swaps_v1.sql:707-743 (tk_commit_task)`
- **How it goes wrong:** 1. Change a member's status to inactive. 2. Call the security-assignment or officer task-commit endpoint with that member ID. 3. The RPC accepts the same-chapter row and creates active commitment/outbox/audit state. 4. The event appears staffed by someone who cannot act.
- **Why it matters / blast radius:** Operational responsibility, notifications, contribution scoring, and security staffing can be attributed to people who cannot authenticate or are no longer chapter participants. — Officer-assigned jobs, security assignments/swaps, and initiative chair rosters.
- **Tests catch it?** No. Tests cover cross-chapter members and active duplicate assignments, but no inactive/invited targets or status changes between swap request and acceptance.
- **Fix:** Centralize an `active member in chapter` predicate and enforce it in every assignment/target RPC, including revalidation at swap acceptance. Decide how deactivation reconciles existing commitments and chair roles. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: upgraded P1
- **Lead note:** Refuter (Gemini) upgraded to P1 and proved it with a written test. Lead keeps P2: operational, not financial or security. Disputed.

<a id="f-056"></a>
#### F-056 · 🟡 P2 · confirmed · treasury dashboard
**Member treasury dashboard has a 2N invoice query loop on top of cache recomputation**

- **What happens:** Opening the dashboard for 20 open dues/fine invoices causes about 51 SQL operations for the member path. The SPA calls this endpoint on every authenticated initial load.
- **Where:** `api/treasury/services/member_dashboard.py:27-47 (_net_allocated_cents and _direct_paid_cents)`, `api/treasury/services/member_dashboard.py:50-132 (get_member_dashboard)`, `api/treasury/core/balance.py:75-170 (BalanceEngine member recomputation)`, `api/treasury/api/balances.py:48-74 (get_member_treasury_dashboard)`
- **How it goes wrong:** 1. A member accumulates 25 open or partially paid invoices. 2. They load the SPA. 3. The dashboard recomputes all balances and issues 50 per-invoice payment/allocation reads. 4. Other concurrent initial-load requests compete for the same per-process pool and blocked event loop.
- **Why it matters / blast radius:** Twenty to fifty open invoices is realistic across terms. Latency and pool pressure grow with financial history rather than the small response size. — Every member login and every officer inspection of a member with multiple open invoices.
- **Tests catch it?** partial — `tests/treasury/test_v1_balance_submissions.py` asserts dashboard values with one open invoice but does not count queries or exercise a multi-invoice history.
- **Fix:** Fetch allocations and direct payments for all invoice IDs in two bulk queries and group in Python, or calculate remaining amounts in one SQL/RPC query. Avoid recomputing the cache during a read once write paths own cache invalidation. · scope: **small**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2 · **also reported as:** lead session: Balance cache is recomputed on every read (5 queries per mem
- **Lead note:** Balance recompute on read plus 2N loop.

<a id="f-057"></a>
#### F-057 · 🟡 P2 · confirmed · treasury fines
**Manual fine issuance expands to approximately eight committed database operations per member**

- **What happens:** Issuing M fines costs about 8M database operations after preflight. Each member is its own transaction boundary, so a failure at member 51 leaves the first 50 committed even though the request fails.
- **Where:** `api/treasury/api/fines_legacy.py:173-224 (issue_fines)`, `api/treasury/services/invoices.py:62-104 (create_invoice_v2)`, `api/treasury/core/balance.py:75-142 (_member_figures)`, `api/treasury/core/balance.py:147-170 (recompute_member)`
- **How it goes wrong:** 1. An officer selects 100 unexcused members. 2. The endpoint successfully creates and notifies 50 invoices. 3. A pool or DB failure occurs on member 51. 4. The request returns 500 with 50 fines already committed. 5. The officer retries without knowing the partial result, forcing another full preflight and per-member loop.
- **Why it matters / blast radius:** A single required-event fine run can target most of a 50-150 member chapter. The endpoint becomes slow and exposes an officer to an ambiguous partial result; retries converge through idempotency but do not explain what happened. — Every member selected in one fine run and the officer-facing request; load scales linearly with a high constant.
- **Tests catch it?** partial — `tests/treasury/test_v1_fines.py` verifies one- and two-member happy paths and idempotent reissue, but has no large-batch query budget or injected mid-loop failure test.
- **Fix:** Extend the existing bulk RPC to accept `source_event_id`, per-member deterministic keys, and transactional outbox rows. Return explicit created/skipped results from one transaction, then refresh affected caches in a bounded bulk operation. · scope: **medium**
- **Found by:** Codex · **verified by:** refute@agy: confirmed P2

<a id="f-058"></a>
#### F-058 · 🟡 P2 · confirmed · treasury rebuild
**Rebuild can call the ledger clean when a missing payment row and an extra payment row share an amount and a member**

- **What happens:** Two genuine $25 payments by the same member compare equal as a count, which is why the 0012 source mismatch does not false-alarm. The same key means a live ledger that is missing payment A's row and contains an extra payment row of the same amount for the same member (or an invalidated row excluded by the status='active' filter, paired with a stray active row) produces equal counts and is_clean is true. Other entry types still match on source_id. Rebuild never deletes or rewrites big_ledger.
- **Where:** `api/treasury/core/rebuild.py:23-27`, `api/treasury/core/rebuild.py:126-136 (_ledger_key)`, `api/treasury/core/rebuild.py:138-161 (_diff_ledger)`, `migrations/0012_fines_to_invoices_migration.sql:47-51`
- **How it goes wrong:** 1. Member has two verified payments of 2500 cents, each with its own PAYMENT_RECEIVED. 2. Owner invalidates payment A's ledger row (trigger allows active→invalidated; no audit row). 3. Owner inserts a different active PAYMENT_RECEIVED of 2500 for the same member, source pointing at nothing. 4. rebuild() counts PAYMENT_RECEIVED/(2500, member) as 2 reconstructed and 2 live. ledger_drift is empty for that pair. The orphan and the hole cancel.
- **Why it matters / blast radius:** Rebuild is the only drift detector, and the payment leg is the one 0012 had to special-case. A treasurer who runs rebuild and sees a clean report has not actually tied each PAYMENT_RECEIVED row to a verified payment. Balance drift is a separate comparison and can still be clean, because balances rea — Drift reports for every chapter. Does not by itself move money. It hides a class of ledger corruption that the rest of the diff would catch.
- **Tests catch it?** partial. tests/treasury/test_chunkG_rebuild_hardening.py covers the 0012 source-table exception and asserts rebuild does not rewrite the ledger. It does not assert that two same-amount payments are distinguished by source_id.
- **Fix:** Key PAYMENT_RECEIVED on source_id like the other types, and teach the diff to accept the single 0012 shape (source_table=unpaid_invoices and source_id=the payment's invoice_id) as an alias for that verified payment. Do not collapse unrelated rows. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: confirmed P2

<a id="f-032"></a>
#### F-032 · 🟡 P2 · confirmed · treasury verify / greekos dues
**The payment the member submits against one invoice is applied oldest-first to a different invoice**

- **What happens:** The review queue shows the invoice on the submission. Verify treats every submission as a balance payment and walks open invoices oldest first. Surplus is credit, by design. The targeted invoice is not preferred even for the first cent.
- **Where:** `migrations/0124_treasury_v1_allocations.sql:192-218 (tr_verify_payment_v2 allocation loop)`, `api/treasury/api/payments.py:169-183 (verify_payment_v1)`, `greekos/src/api.ts:631-660 (submitPaymentProof, verifyPaymentSubmission)`, `greekos/src/lib/dues.ts:189-211 (planProof)`
- **How it goes wrong:** 1. Member has dues invoice created Monday ($250) and a fine created Tuesday ($25). 2. Member submits proof from the fine row: planProof sets invoice_id to the fine, amount 2500. 3. Officer clicks verify. handleVerifyProof calls verify-v1 with no Idempotency-Key (safe against double-verify because of FOR UPDATE, not against mis-allocation). 4. v2 allocates $25 to the Monday dues invoice. Fine status stays unpaid. 5. Standing still counts the fine. The member's proof note and the queue invoice id say the fine was the thing being paid.
- **Why it matters / blast radius:** A member who pays a $25 fine while an older dues invoice is open has the fine left unpaid and the dues reduced. The officer approved a row that names the fine. Standing keys off unpaid fines, so the member can still be in warning for a fine they tried to pay, while dues they did not mean to pay shri — Every verify done from the current SPA. Balance-level submissions are the same allocator, which matches their shape; invoice-targeted submissions are the mismatch.
- **Tests catch it?** partial. tests/treasury/test_v1_allocation.py::test_verify_v2_works_for_invoice_targeted_submissions asserts the ignore-target behavior, so the suite will fail if verify starts honoring invoice_id. Nothing tests that the invoice shown to the reviewer
- **Fix:** In tr_verify_payment_v2, if submission.invoice_id is set and that invoice is still open, allocate there first and only then oldest-first for the remainder. Or stop collecting invoice_id and label the queue as a balance payment. · scope: **small**
- **Found by:** Cursor/Grok · **verified by:** refute@codex: downgraded P2
- **Lead note:** Refuter (Codex) downgraded: money lands on the right member; oldest-first is the documented rule. The UI still implies invoice-specific payment.

<a id="f-059"></a>
#### F-059 · 🟡 P2 · confirmed · treasury/fines
**Legacy POST /api/fines/process-event bypasses V1 fine rules**

- **What happens:** Two coexisting fine pipelines produce different invoices and audit rows without actor
- **Where:** `api/treasury/services/fine_processor.py:17-105 (process_event_fines)`, `api/treasury/api/fines_legacy.py`
- **How it goes wrong:** 1. Two officers click 'process fines' at once. 2. Both read no existing fines. 3. Both insert.
- **Why it matters / blast radius:** Double fines on concurrent calls; audit rows with no actor — Fines
- **Tests catch it?** Partial
- **Fix:** Delete the legacy path or route it through the V1 rule with idempotency keys · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P2

<a id="f-060"></a>
#### F-060 · 🟡 P2 · confirmed · treasury/fines, tasks
**Naive event times treated as UTC in fine and task timing**

- **What happens:** Fines become eligible hours early or late depending on the chapter's timezone
- **Where:** `api/treasury/api/fines_legacy.py:38-46 (_event_start_utc), :182-190`, `migrations/0110, 0142, 0144, 0145 (hours_before_event)`
- **How it goes wrong:** 1. Event at 20:00 local (PDT). 2. Backend treats it as 20:00 UTC = 13:00 local. 3. 24 h gate opens 7 h early.
- **Why it matters / blast radius:** Wrong fine timing; T-36 unclaim boundaries drift — All chapters not in UTC
- **Tests catch it?** No
- **Fix:** Store event start as timestamptz or attach the chapter timezone once, centrally · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: confirmed P2 · **also reported as:** Gemini Pro: Frontend treats naive datetimes as local time while backend ; Codex: Browser and database compute the T-36 unclaim boundary in di; Cursor/Grok: The 36-hour unclaim lock casts naive event and initiative lo
- **Lead note:** Naive local times treated as UTC (backend) or local (frontend); T-36 lock, fine gate.

</details>


### 🔵 P3 — 14 findings

| ID | Subsystem | One line | Confidence | Fix size |
|---|---|---|---|---|
| [F-061](#f-061) | App.tsx | FinanceModule remounts entire subtree on member change | confirmed | surgical |
| [F-062](#f-062) | AttendanceModule | Roll call attendance buttons lack radiogroup grouping and accessible names | confirmed | small |
| [F-001](#f-001) | CommandModule | Command Console fakes Natural Language parsing with fragile regex | confirmed | medium |
| [F-063](#f-063) | announcements/cron | Import cycle announcements ↔ cron; message templates live in cron/core | confirmed | surgical |
| [F-064](#f-064) | api | Raw exception text in HTTP responses | confirmed | surgical |
| [F-065](#f-065) | chapters | Email enumeration and spam via unauthenticated POST /api/chapters | confirmed | surgical |
| [F-066](#f-066) | frontend tooling | Frontend package metadata retains unused AI/scaffold dependencies and duplicate Vite owner | confirmed | surgical |
| [F-045](#f-045) | greekos hooks | Optimistic UI claims success before the server confirms; backendDown drops mutations silen | confirmed | small |
| [F-067](#f-067) | observability/logging | Request IDs are not injected into ordinary service logs | confirmed | small |
| [F-052](#f-052) | rbac | Tautological Mocking in RBAC Tests via FakeSb | confirmed | small |
| [F-068](#f-068) | sms consent | Twilio START re-grants SMS consent on every member row with that phone across chapters | likely | surgical |
| [F-069](#f-069) | tests | Test database accumulates state across tests without truncation | confirmed | architectural |
| [F-070](#f-070) | treasury | Idempotency keys are client-chosen, never expire and do not hash the payload | confirmed | small |
| [F-071](#f-071) | treasury core / platfo | Test-era treasury abstractions and compatibility stubs remain presented as production arch | confirmed | small |

<details><summary>▸ P3 cards (14)</summary>

<a id="f-061"></a>
#### F-061 · 🔵 P3 · confirmed · App.tsx
**FinanceModule remounts entire subtree on member change**

- **What happens:** Instead of reacting to prop changes, the entire `FinanceModule` is forcefully unmounted and remounted every time the viewed member changes.
- **Where:** `greekos/src/App.tsx:176`
- **How it goes wrong:** 1. Officer switches 'View As' dropdown. 2. React destroys DOM nodes for the entire Finance tab and recreates them, dropping any scroll position or local UI state.
- **Why it matters / blast radius:** Antipattern that breaks React's reconciliation engine and wastes rendering cycles. — Performance degradation and loss of transient state on view switch.
- **Tests catch it?** no
- **Fix:** Remove the `key` prop and allow React to naturally reconcile `FinanceModule` props. · scope: **surgical**
- **Found by:** Gemini Pro · **verified by:** lead only

<a id="f-062"></a>
#### F-062 · 🔵 P3 · confirmed · AttendanceModule
**Roll call attendance buttons lack radiogroup grouping and accessible names**

- **What happens:** Screen readers read individual toggle buttons without associating them with the specific member's row or grouping them as a set of mutually exclusive options. The Modal component allows keyboard focus to escape the overlay.
- **Where:** `greekos/src/components/AttendanceModule.tsx:252-270`, `greekos/src/components/ui/Modal.tsx:22`
- **How it goes wrong:** 1. Visually impaired user tabs into Roll Call table. 2. Hears 'Present, toggle button', lacking context of which member this applies to.
- **Why it matters / blast radius:** Violates WCAG requirements and makes core features inaccessible to disabled officers. — Severe accessibility degraded experience for keyboard and screen reader users.
- **Tests catch it?** no
- **Fix:** Wrap attendance buttons in a `role=\"radiogroup\"` with an `aria-label` specifying the member name, use `role=\"radio\"` and `aria-checked` on buttons. Add `focus-trap-react` to Modal. · scope: **small**
- **Found by:** Gemini Pro · **verified by:** lead only

<a id="f-001"></a>
#### F-001 · 🔵 P3 · confirmed · CommandModule
**Command Console fakes Natural Language parsing with fragile regex**

- **What happens:** Despite claiming to accept 'plain English' and importing `@google/genai` in `package.json`, the Command Console only parses exact hardcoded string regex patterns like `fine [name] $[amount]`.
- **Where:** `greekos/src/components/CommandModule.tsx:40-100`
- **How it goes wrong:** 1. User types 'charge Cody 25 bucks for missing meeting'. 2. Regex fails to match `fine ... $X`. 3. Returns 'Command syntax not recognized'.
- **Why it matters / blast radius:** Fails to deliver the promised AI workflow feature, leading to false capabilities and user confusion. — Core AI feature is completely non-functional for general NLP input.
- **Tests catch it?** no
- **Fix:** Wire the `CommandModule` to a real backend endpoint (`/api/nl-controller`) that utilizes the GenAI SDK to translate user intent into structured RPC calls. · scope: **medium**
- **Found by:** Gemini Pro · **verified by:** refute@cursor: downgraded P3
- **Lead note:** CLAUDE.md hard rule: no fabricated business logic; refute checks whether it is presented as real. Refuter (Grok) downgraded P1→P3: parser is fail-closed keyword grammar, the problem is overclaiming copy and an unused AI dependency. Lead agrees.

<a id="f-063"></a>
#### F-063 · 🔵 P3 · confirmed · announcements/cron
**Import cycle announcements ↔ cron; message templates live in cron/core**

- **What happens:** Package cycle
- **Where:** `api/announcements/services/outbox.py:15`, `api/announcements/services/sms.py:40`, `api/cron/services/outbox_drain.py:45`
- **How it goes wrong:** n/a
- **Why it matters / blast radius:** Fragile imports; templates in the wrong package — Two packages
- **Tests catch it?** No
- **Fix:** Move templates to api/platform or announcements/core · scope: **surgical**
- **Found by:** lead session · **verified by:** lead only

<a id="f-064"></a>
#### F-064 · 🔵 P3 · confirmed · api
**Raw exception text in HTTP responses**

- **What happens:** Internal SQL/RPC text reaches clients
- **Where:** `api/treasury/api/fines_legacy.py:247-248`, `api/treasury/api/payments.py:230-231`, `api/auth/api/auth.py:392-393`, `api/treasury/api/invoices.py:119`
- **How it goes wrong:** 1. Trigger any RPC error. 2. Read the message.
- **Why it matters / blast radius:** Information leak; brittle client behaviour — API
- **Tests catch it?** No
- **Fix:** Map RPC errors to fixed messages in one helper · scope: **surgical**
- **Found by:** lead session · **verified by:** lead only · **also reported as:** Cursor/Grok: Roster import tells an officer which emails belong to anothe

<a id="f-065"></a>
#### F-065 · 🔵 P3 · confirmed · chapters
**Email enumeration and spam via unauthenticated POST /api/chapters**

- **What happens:** Anyone can test whether an email is a member and trigger emails
- **Where:** `api/chapters/api/chapters.py:51-57`, `api/chapters/auth.py:26-46`
- **How it goes wrong:** 1. POST /api/chapters with target email. 2. Read 409 vs 201.
- **Why it matters / blast radius:** Enumeration + outbox spam — Public
- **Tests catch it?** No
- **Fix:** Uniform response; persisted rate limit; captcha or invite-only · scope: **surgical**
- **Found by:** lead session · **verified by:** lead only

<a id="f-066"></a>
#### F-066 · 🔵 P3 · confirmed · frontend tooling
**Frontend package metadata retains unused AI/scaffold dependencies and duplicate Vite ownership**

- **What happens:** Installs include packages unrelated to the shipped SPA and the manifest does not identify the product. Tool ownership is ambiguous because Vite is declared twice.
- **Where:** `greekos/package.json:1-33 (package manifest)`
- **How it goes wrong:** 1. A developer audits the manifest and assumes the client performs Gemini work or animation. 2. They preserve/configure unused packages or add code around them. 3. Lockfile updates and vulnerability reviews continue to include dependencies with no product consumer.
- **Why it matters / blast radius:** This increases dependency/supply-chain surface and makes it harder to distinguish intentional product capabilities from generated-template residue. `@google/genai` is particularly misleading in a product whose NL/bylaws features are explicit stubs. — Frontend installs, dependency updates, security review, and developer understanding; no current user-facing failure.
- **Tests catch it?** no — lint, node tests, build, and the baseline dependency audit can all pass with unused dependencies and stale package metadata.
- **Fix:** Confirm with the package manager's dependency graph, remove unused direct dependencies, keep Vite only in devDependencies, and rename the package to `greekos` or `guildos-web`. · scope: **surgical**
- **Found by:** Codex · **verified by:** lead only

<a id="f-045"></a>
#### F-045 · 🔵 P3 · confirmed · greekos hooks
**Optimistic UI claims success before the server confirms; backendDown drops mutations silently**

- **What happens:** User sees success for actions that failed or were never sent
- **Where:** `greekos/src/hooks/useEvents.ts:132-133, 156-157, 183-184, 207-208, 231-232, 255-256, 288-289`, `greekos/src/hooks/useAppData.ts:241-245`, `greekos/src/hooks/useBackend.ts:21`
- **How it goes wrong:** 1. Backend down. 2. Officer edits event. 3. Toast success; reload: unchanged.
- **Why it matters / blast radius:** Lost edits — All mutations
- **Tests catch it?** No
- **Fix:** Toast after await; surface failures; block when backend is down · scope: **small**
- **Found by:** lead session · **verified by:** refute@codex: downgraded P3 · **also reported as:** Gemini Pro: Optimistic mutations show success before API resolution and 
- **Lead note:** Refuter (Codex) downgraded P2→P3: syncApi rolls back and replaces the toast on an API error; only the backendDown branch is silent. Lead agrees.

<a id="f-067"></a>
#### F-067 · 🔵 P3 · confirmed · observability/logging
**Request IDs are not injected into ordinary service logs**

- **What happens:** Responses expose X-Request-ID, but most warnings and errors cannot be searched by that ID. Cron row failures are caught and return HTTP 200 counts, so they bypass the one handler that logs the ID.
- **Where:** `api/observability.py:29-52 (request context and logging format)`, `api/observability.py:81-115 (request middleware and exception handler)`, `api/cron/services/outbox_drain.py:271-280 (_deliver_row error logging)`
- **How it goes wrong:** 1. A cron request receives request ID R. 2. Several rows fail inside `_deliver_row`. 3. The service catches and logs them without R, then returns 200. 4. An operator searches logs for R and finds no row failures.
- **Why it matters / blast radius:** Operators cannot reliably correlate a user report or cron invocation with its database/provider logs, increasing diagnosis time for intermittent failures. — All handled service failures and routine request logs.
- **Tests catch it?** no — no observability test asserts request IDs on service log records.
- **Fix:** Install a logging filter that adds `request_id` to every record and include it in the format/structured JSON fields. Log one structured cron summary even for empty runs. · scope: **small**
- **Found by:** Codex · **verified by:** lead only

<a id="f-052"></a>
#### F-052 · 🔵 P3 · confirmed · rbac
**Tautological Mocking in RBAC Tests via FakeSb**

- **What happens:** The FakeSb query builder mock ignores all .eq filter arguments and unconditionally returns canned rows.
- **Where:** `tests/rbac/test_permissions_service.py:73-83`, `tests/rbac/test_one_gate.py:73-83`
- **How it goes wrong:** If the python tenant filter is removed, privilege escalation occurs, but FakeSb tests mask the bug.
- **Why it matters / blast radius:** The RBAC tests verify nothing about the actual SQL queries sent to the database. A developer could accidentally delete the tenant filter in the permission check, and the tests would still pass. — Privilege escalation across chapters.
- **Tests catch it?** no
- **Fix:** Replace FakeSb with the real test database fixture (sb_client) or a stricter mock that asserts .eq is called with the correct arguments. · scope: **small**
- **Found by:** Gemini Pro · **verified by:** refute@cursor: refuted P4
- **Lead note:** Refuter (Grok) refuted the security implication: FakeSb tautology is real but member_id scoping plus RPC writer guards mean no tenant hole. Lead keeps it as a P3 test-quality item.

<a id="f-068"></a>
#### F-068 · 🔵 P3 · likely · sms consent
**Twilio START re-grants SMS consent on every member row with that phone across chapters**

- **What happens:** One person's START flips consent for same-phone rows in other chapters
- **Where:** `api/announcements/api/twilio_inbound.py:106-125`
- **How it goes wrong:** 1. Same phone in chapters A and B. 2. START from that phone. 3. Both rows consented.
- **Why it matters / blast radius:** Cross-tenant side effect — SMS
- **Tests catch it?** Unknown
- **Fix:** Scope by chapter or treat as global consent explicitly · scope: **surgical**
- **Found by:** lead session · **verified by:** lead only

<a id="f-069"></a>
#### F-069 · 🔵 P3 · confirmed · tests
**Test database accumulates state across tests without truncation**

- **What happens:** Tests create a new chapter_id for isolation but never clean up rows, causing the test database to grow unbounded with stale test data.
- **Where:** `tests/treasury/conftest.py:121-127`
- **How it goes wrong:** Over time, the test database becomes bloated and slow, leading to flaky tests or forcing manual tear-downs.
- **Why it matters / blast radius:** While assertions are scoped to chapter_id, global queries (e.g. outbox drain limit queries) will scan increasingly large tables, potentially masking performance issues or causing timeouts over time. — Developer velocity and CI reliability.
- **Tests catch it?** partial
- **Fix:** Implement a database reset strategy for the test database (e.g., using template databases or truncating with CASCADE bypassing the append-only triggers during teardown). · scope: **architectural**
- **Found by:** Gemini Pro · **verified by:** lead only

<a id="f-070"></a>
#### F-070 · 🔵 P3 · confirmed · treasury
**Idempotency keys are client-chosen, never expire and do not hash the payload**

- **What happens:** Silent no-op on a changed retry
- **Where:** `migrations/0080_treasury_tenant_guards.sql (idempotency_keys)`, `greekos/src/components/finance/DuesRunModal.tsx:27`
- **How it goes wrong:** 1. Submit dues run with key K, amount 100. 2. Edit to 120, same key. 3. Server returns the 100 result.
- **Why it matters / blast radius:** Wrong amounts silently ignored — Treasury
- **Tests catch it?** No
- **Fix:** Store a payload hash with the key; reject mismatches; expire keys · scope: **small**
- **Found by:** lead session · **verified by:** lead only

<a id="f-071"></a>
#### F-071 · 🔵 P3 · confirmed · treasury core / platform
**Test-era treasury abstractions and compatibility stubs remain presented as production architecture**

- **What happens:** The source tree advertises writer, pagination, service-seam, observability, and auth-admin abstractions that runtime code does not use. Some remain because early foundation tests instantiate them directly.
- **Where:** `api/treasury/core/audit.py:10-47 (AuditAction and AuditLogger)`, `api/treasury/core/ledger.py:13-87 (LedgerWriter)`, `api/treasury/core/idempotency.py:5-11 (idempotency_operation)`, `api/treasury/api/pagination.py:1-13 (Page)`
- **How it goes wrong:** 1. A developer follows `docs/CODEMAP.md` to `LedgerWriter` as the sanctioned ledger boundary. 2. They use it in a new route. 3. The new flow writes ledger rows outside the business RPC, without the operational row and audit in one transaction. 4. Foundation tests pass because they were written around the obsolete helper.
- **Why it matters / blast radius:** Agent sessions are likely to extend these apparent sanctioned abstractions, creating a second write path that bypasses current RPC invariants or building on a no-op stub. — Future treasury, task-standing, observability, pagination, or invitation work; little immediate runtime impact until a dead abstraction is reused.
- **Tests catch it?** partial — `tests/treasury/test_chunk0_foundations.py` actively tests the obsolete writers, which helps preserve them; no production integration test requires them. The other listed symbols have zero callers in `api` and `greekos/src`.
- **Fix:** Mark test-only fixtures as such or replace their tests with RPC invariant tests. Remove empty/zero-caller public-looking symbols after one release-wide reference check, and update the codemap so RPCs are the only advertised financial writers. · scope: **small**
- **Found by:** Codex · **verified by:** lead only

</details>

### Dropped after refutation

| ID | Claim | Why dropped |
|---|---|---|
| F-035 | Frontend DTOs have drifted from backend schemas | The three cited "drifts" were GET-vs-POST contracts and an alias field; nothing the UI needs is missing. |
| F-049 | Money regex rejects `.5`; preview clamps credits to zero | Both are specified and unit-tested behaviour (`transaction.test.ts:14, 21-27`). |
| F-055 | Treasury v1 tests mock the balance engine | Verify and reallocate call `BalanceEngine` directly and the test asserts the cache row; only invoice-create/void recompute is stubbed. |

## 4 · Top critical findings

**In short:** the Top 10 table on page one. Two lines of context for each.

1. **F-022 · legacy role wins over RBAC.** `get_member_permissions` unions `LEGACY_ROLE_COMPAT[members.role]` with `member_roles`; `rbac_revoke_role` deletes only from `member_roles`. Every officer ever created through the roster or legacy PUT keeps officer rights until someone also flips the column.
2. **F-023 · no grant ceiling.** The seeded `officer` role holds `roles:assign` and `rbac_assign_role` checks only that the caller has that key. `MemberRolesPanel` lists the whole catalog including `admin`.
3. **F-014 · Finance tab does not save.** Four handlers in `useFinance.ts` mutate React state, build a fake ledger and toast success. Flagged in the 2026-08-20 review; still present.
4. **F-027 · self-dealing.** `tr_create_adjustment` and both verify RPCs never compare the actor to the beneficiary. Below $500 no second signature is needed.
5. **F-024 · standing reads the wrong fine set.** `load_member_engagement` filters `status='unpaid'` at full `amount_cents`; `partially_paid` fines disappear. F-015: an early return when no past required event exists skips fines entirely. F-002: `date <= now()` counts today's evening event as missed at 9 am.
6. **F-028 · stale balance cache.** `dashboard_summary`, the CSV export and the "members with balance" SMS audience read `member_finance_accounts`; `at_review_excuse` voids a fine in SQL and never recomputes it.
7. **F-011 · autocommit everywhere.** `QueryBuilder.execute` sets `autocommit=True`; `update_event`, `create_task`, chapter onboarding, roster import, link and phone check-in are all two-or-more-statement sequences with no transaction.
8. **F-019 · at-least-once with no dedup at the provider.** The drain calls Twilio/SMTP, then updates the row in a second commit; a crash in between resends. F-017: `dispatch_send` sends the same pending rows inline while the cron may be sending them too.
9. **F-010 · production is a mystery.** `Prod/api` differs in 19 files and lacks 21; `Prod/migrations` has 2 files; `PROD_PROJECT_REFS` is empty; migration tracking is by filename only and two migrations were edited after apply (F-016).
10. **F-037 · plaintext codes in the outbox.** `notify_code` puts the setup/reset code in the `message_outbox` payload. Failed rows keep it for the 7-day code lifetime; the officer view redacts it, the table does not.

## 5 · Security findings

**In short:** authentication is solid; authorization is undermined by a legacy column; tenant isolation is Python filters plus RPC guards, which held up under a route-by-route sweep; the sharp edges are self-service and break-glass paths.

| ID | Sev | Finding | Preconditions | Tests catch it? |
|---|---|---|---|---|
| [F-022](#f-022) | 🟠 | RBAC revoke does not revoke (legacy `members.role` union) | any member with `members.role='officer'` | no |
| [F-023](#f-023) | 🟠 | No grant ceiling on `roles:assign` | one officer login | no |
| [F-006](#f-006) | 🟠 | Roster CSV stamps `role=officer` for every non-member role | an officer imports a CSV with `treasury_viewer` | no |
| [F-027](#f-027) | 🟠 | Officers can credit themselves (adjustment < $500; self-verify) | `treasury:adjustment:create` or `treasury:payment:verify` | no |
| [F-005](#f-005) | 🟠 | Unused setup/reset codes stay valid after a password change; redeem does not bump `token_version` | a leaked older code | partial |
| [F-037](#f-037) | 🟠 | Plaintext codes in failed outbox rows for 7 days | database read access | no |
| [F-007](#f-007) | 🟠 | Production guard, dev-login lock and signup limiter arm only when `VERCEL_ENV` is set | any non-Vercel deploy | `test_production_guard.py` covers Vercel only |
| [F-008](#f-008) | 🟠 spec. | anon/authenticated may hold DML on non-RLS tables via the Supabase Data API | Data API enabled (dashboard) | no |
| [F-026](#f-026) | 🟠 | Self-vs-other checks compare `str` to `UUID` and fail closed (jobs claim 403s for members) | any member | no |
| [F-025](#f-025) | 🟠 | Generic task-status endpoint bypasses report/approve lifecycle | `tasks:complete` | no |
| [F-036](#f-036) | 🟡 | Unauthenticated phone check-in marks any member who shares the phone; anyone with the live code can check in a friend | live short code | partial |
| [F-020](#f-020) | 🟡 | Break-glass password reset targets any `DATABASE_URL` and does not revoke sessions | operator shell | no |
| [F-048](#f-048) | 🟡 | Unbounded usage-event appends; immutability trigger also blocks cascaded deletes | any login | no |
| [F-065](#f-065) | 🔵 | Email enumeration and outbound spam via `POST /api/chapters` | none | no |
| [F-064](#f-064) | 🔵 | Raw exception text in responses | any RPC error | no |
| [F-068](#f-068) | 🔵 | Twilio START flips consent on every row with that phone across chapters | shared phone | `test_twilio_inbound.py` documents it |

Checked and clean: JWT algorithm/issuer/audience pinning; constant-time secret compares for cron, platform and Twilio; no cookie writer, so CSRF does not apply; no request-controlled identifier reaches the SQL builder; check-in HTML escapes event text; setup codes bcrypt-hashed at rest (except F-037); `npm audit` clean; no SSRF or command execution surface found.

## 6 · Financial and database findings

**In short:** money is never lost inside a `tr_*` function. It is misread afterwards. The readers (standing, dashboards, reminders) and the two coexisting verify paths are where a member can owe the wrong amount or be punished for a paid fine.

| ID | Sev | Finding | Money at risk? |
|---|---|---|---|
| [F-024](#f-024) | 🟠 | Partial payment removes a fine from standing | standing, not money |
| [F-015](#f-015) | 🟠 | No past required event → all fines ignored by standing | standing |
| [F-028](#f-028) | 🟠 | Dashboards, CSV, reminder SMS read a cache that excuse approval never refreshes | wrong totals shown and messaged |
| [F-029](#f-029) | 🟠 | v1 verify writes invoice status from `verified_payments`; v2 from `payment_allocations`; reallocating a v1 payment desyncs them | invoice can read paid/unpaid wrongly |
| [F-030](#f-030) | 🟠 | Refund raises what the member owes but does not reopen the invoice; SPA can only pay an invoice | member cannot settle |
| [F-031](#f-031) | 🟠 | Balance is computed from mutable tables; the append-only ledger is not the source | auditability, not totals |
| [F-027](#f-027) | 🟠 | Self-credit below $500 | yes |
| [F-004](#f-004) | 🟠 | Excused and fined can both stand; `at_set_attendance excused` never voids | wrong fines |
| [F-032](#f-032) | 🟡 | Payment for invoice A is allocated oldest-first to invoice B; UI implies A | standing |
| [F-058](#f-058) | 🟡 | Rebuild can report the ledger clean when a missing and an extra row cancel out | auditability |
| [F-059](#f-059) | 🟡 | Legacy `process-event` fines path: null idempotency key, null actor, NUMERIC amount | duplicate fines |
| [F-060](#f-060) | 🟡 | Naive event times treated as UTC: 24 h fine gate and T-36 lock drift by the timezone offset | early/late fines |
| [F-057](#f-057) | 🟡 | ~8 commits per fine issued | partial batches |
| [F-070](#f-070) | 🔵 | Idempotency keys never expire and do not hash the payload | replay returns stale result |

Database-level summary: integer cents and append-only history are enforced; fine uniqueness, excuse/fine exclusion, role column agreement, and migration integrity (F-016: 0147 and 0149 edited after apply, filename-only tracking) are not. RLS is defense-in-depth that is never exercised (F-009).
## 7 · Test-suite assessment

**In short:** the suite is real (1030 backend tests against a real database) and protects the treasury RPCs, auth and the outbox well. It cannot see tenant isolation or row-level security because every test connects as superuser, and the RBAC and balance tests mock the exact thing they claim to test.

### 7.1 Twenty-five representative tests

| Test | Can detect | Misses | Value |
|---|---|---|---|
| `tests/treasury/test_chunkC_payments.py` | double-verify races, allocation math | RLS, HTTP authorization (superuser DB) | High |
| `tests/treasury/test_chunkH_tenant_guards.py` | missing `chapter_id` guards in RPC bodies | RLS (superuser) | Moderate |
| `tests/rbac/test_permissions_service.py` | data-shape transforms only | any real filter: `FakeSb` ignores `.eq()` entirely | Low, tautological |
| `tests/rbac/test_one_gate.py` | role resolution shape | real DB behaviour (`FakeSb`) | Low |
| `tests/attendance/test_checkin_page_escaping.py` | XSS in the check-in template | lookup failures (DB fully mocked) | Low |
| `tests/treasury/test_v1_allocation.py` | invoice state transitions | balance derivation (`recompute_member_balance` mocked) | Low, over-mocked |
| `tests/treasury/test_v1_void.py` | void transition | balance recalculation (mocked) | Low |
| `tests/auth/test_login_password.py` | brute force, rate-limit bypass, enumeration | — | High |
| `tests/auth/test_invite_setup_codes.py` | code reuse, expiry | — | High |
| `tests/attendance/test_checkin_flow.py` | end-to-end HTTP check-in | RLS | Moderate |
| `tests/events/test_security.py` | swap lifecycle flaws | HTTP auth, RLS | Moderate |
| `tests/tasks/test_jobs_lifecycle.py` | fill state, T-36h lock | HTTP auth, RLS | Moderate |
| `tests/cron/test_drain_outbox.py` | claim, batch, reaper, failed rows | double-sender race with inline SMS | High |
| `tests/cron/test_drain_email.py` | email formatting, conditional send | — | High |
| `tests/cron/test_cron_auth.py` | bypassable cron auth | — | Moderate |
| `tests/announcements/test_sms_send.py` | recipient counting, consent | — | Moderate |
| `tests/chapters/test_create_chapter.py` | bad bootstrap data, rate-limit bypass | — | High |
| `tests/chapters/test_roster_import.py` | rollback on failure, CSV parsing | — | High |
| `tests/contribution/test_standing_firewall.py` | import cycles (AST check) | runtime behaviour | Low, brittle |
| `tests/config/test_production_guard.py` | dev defaults in production | non-Vercel deploys | Moderate |
| `tests/services_scaffold/test_route_registration.py` | missing OpenAPI paths | anything the route does | Low |
| `tests/test_db_guard.py` | bad DB URL parsing | real connection validation | Moderate |
| `greekos/src/lib/dues.test.ts` | dues-run payload derivation | backend validation | Moderate |
| `greekos/src/lib/balance.test.ts` | balance state extraction | integration | Moderate |
| `greekos/src/components/events-access.test.ts` | permission-gated rendering | DOM events | Moderate |

### 7.2 Highest-value missing tests

| Missing test | Would catch |
|---|---|
| Any test that connects as a non-owner role | whether the 42 RLS policies do anything at all |
| Revoking `officer` via RBAC removes officer permissions | F-legacy-role (the legacy column keeps the grant) |
| Approving an excuse refreshes `member_finance_accounts` | stale balance after a fine is voided |
| Inline SMS send and cron drain do not both deliver the same row | double SMS |
| Link and phone check-in write an `audit_logs` row | silent attendance edits |
| A second fine for the same event and member is rejected | duplicate fines |
| `recompute_member_balance` end to end (unmocked) after verify, void, refund, reallocate | balance drift |
| Standing with a same-day future event, and with a partially paid fine | both standing bugs |
| A migration file whose content changed after apply fails CI | silent schema drift |
| Concurrent `ev_assign_security` / `in_remove_chair` | duplicate shifts, zero chairs |

### 7.3 Suite-wide patterns

- **Real database, no teardown.** Every test creates its own chapter; tables grow forever on the demo DB. Cheap and honest, but the DB is shared with `npm run dev`.
- **Superuser everywhere.** `db_conn` and `sb_client` bypass RLS and FastAPI auth. Anything the suite says about isolation is about Python filters only.
- **Two mocking anti-patterns.** `FakeSb` in RBAC tests swallows every filter. Treasury v1 tests patch `recompute_member_balance` out, so the balance engine is untested through the HTTP path.
- **Import-graph tests as behaviour tests.** `test_standing_firewall.py` and `test_route_registration.py` assert file structure, not behaviour.
- **Conftest fixtures are good.** 87 shared fixtures across 15 conftests; per-test chapter isolation and dependency-override clients are the right shape.

## 8 · Agent-generated code patterns

**In short:** the repo shows clear signs of many independent agent sessions. The damage is mostly duplication and leftover scaffolding, not wrong logic. Two patterns matter: parallel implementations of the same concern, and documentation that describes plans instead of code.

| Pattern | Evidence | Class |
|---|---|---|
| **Old and new implementations side by side** | `fines` table + `fines_legacy.py` + `fine_processor.py` + disabled `process-fines` cron next to `unpaid_invoices(kind=fine)`; `attendance.py` legacy vs `sessions.py`; `tr_verify_payment` vs `_v2`; operations template engine (0003) vs tasks/jobs/commitments | agent duplication, historical residue |
| **Same helper written many times** | 7 concerns duplicated: RPC-error→HTTP translators, ISO timestamp parsing with `Z` replacement, `str(uuid)` coercion, chapter-scoped member lookup, 5 fetch wrappers in `api.ts`, outbox enqueue wrappers, money formatting | agent duplication |
| **Test-era abstractions shipped as architecture** | `AuditLogger`, `LedgerWriter`, `idempotency_operation`, `Page`, `select_orphaned_proofs` have only test callers; `CODEMAP.md` still points at them | historical residue |
| **Plan identifiers in code comments** | `balance.py` 9 references, `fines_legacy.py` 6, `router.py` 5 to `Chunk A/G`, `B4FEND`, `imp-*`, `decision #` | historical residue |
| **Docs describe intent, not code** | `CLAUDE.md` frontend tree does not exist; `ARCHITECTURE.md` calls the frontend Next.js; ADR-0002 references deleted files; NL controller references `api/services/operations.py` | historical residue |
| **Fabricated behaviour** | Command console parses "natural language" with regexes; Finance "Add transaction" builds a fake ledger client-side; `enqueueOutbox` is a no-op stub still called | accidental complexity that violates the repo's own "no fabricated logic" rule |
| **Scaffold leftovers** | `package.json` named `react-example`, `@google/genai`, `dotenv`, `motion` unused; `vite` in deps and devDeps; `selfcheck.ts`, `parseWhen.check.ts` | historical residue |
| **Hand-copied second tree** | `Prod/api` and `Prod/fratos` maintained by copy | historical residue with production risk |
| **Defensive coercion for a client that no longer exists** | `isinstance(x, str)` datetime branches, `or {}` / `or []` fallbacks left over from the supabase-py era | accidental complexity |

Not agent damage: the three `notifications.py` files in events have distinct jobs; router include order being load-bearing is deliberate; the PostgREST-shaped builder is a real migration seam, if an expensive one.

## 9 · Good architecture worth preserving

**In short:** the treasury and the outbox are the two places where someone thought hard. Keep them.

| What | Where | Why not to refactor casually |
|---|---|---|
| Money moves in one plpgsql transaction with tenant guard, idempotency key, ledger row and audit row | `migrations/0124` (`tr_verify_payment_v2`), `tr_create_invoice_v2`, `tr_void_invoice`, `tr_reallocate_payment` | This is the only atomic write path in the system. Every Python-side "improvement" so far made things less atomic |
| `Money` value object rejects floats; BIGINT cents with CHECKs | `api/treasury/core/money.py`, treasury tables | The one place a float cannot enter |
| Append-only triggers on `big_ledger`, `audit_logs`, receipts, allocations, evidence | `migrations/0005`, `0031`, `0124` | History cannot be edited even by the app role |
| Double-verify closed by `FOR UPDATE` + `UNIQUE(submission_id)` | `migrations/0031:36-68` | A DB-level guarantee; tests cover it |
| Invoice status derived from coverage | `tr_refresh_invoice_status` | Status is a function of data, not a stored opinion |
| Outbox claim: `FOR UPDATE SKIP LOCKED`, reaper, attempt cap | `migrations/0155` | Correct for overlapping cron workers |
| One SMS consent predicate, enforced at preview and both send paths; blast types pinned to the SMS channel by trigger | `api/sms_consent.py`, `outbox_pin_sms_channel` | Legal exposure lives here |
| JWT pins algorithm, issuer, audience; `token_version` epoch; bcrypt setup codes redacted in the outbox view | `api/platform/postgres.py:554-569`, `api/auth` | Auth basics done right |
| Constant-time secret compares for cron, platform and Twilio; boot guard on production config | `api/cron/auth.py`, `api/index.py` | |
| Setup-code redeem is one conditional `UPDATE`; `au_invite_member` writes member and code atomically | `migrations/0148`, `0161` | The pattern the onboarding paths should copy |
| Job capacity, parent exclusivity, one active commitment per member, swap state machine, all in the database | `migrations/0144`, `0145` | Tasks is the second-best domain |
| Standing and contribution are structurally firewalled; engagement is one bulk aggregate | `api/memberadmin/core/engagement.py`, `api/contribution` | Prevents a class of "score leaks into standing" bugs |
| Event visibility is one function reused by list, detail and calendar; events list uses bulk decoration | `api/events/services/events.py:224-377` | No N+1 there |
| Pure adapters in the frontend; `formatMoney` / `dollarsToCents` centralised; pure `lib/*.ts` with tests | `greekos/src/adapters.ts`, `formatters.ts` | The one clean seam in the SPA |
| Explicit `not_implemented` for bylaws and NL controller | `api/bylaws`, `api/nl_controller` | Honest stubs |
| `db_guard.py` fail-closed demo/prod guard; per-file migration transactions; CI on a fresh Postgres | `scripts/` | |

## 10 · Things that look weird but are reasonable

| Looks weird | Why it is fine |
|---|---|
| Balances never read `big_ledger` | The ledger is a shadow audit log by design; `rebuild.py` reports drift. Fix the readers of the cache, not this |
| `unpaid_invoices` holds paid invoices | Historical name for the invoice aggregate; renaming touches 30+ files for no behaviour change |
| `fines_legacy.py` | A URL-compatibility adapter over the current invoice model, not a second fine engine (the second engine is `fine_processor.py`) |
| Three `notifications.py` files in events | Route, enqueue helpers, and service each have one job |
| Router include order is load-bearing | Fixed path segments must register before parameterised ones; the append-only rule in CLAUDE.md is correct |
| `_ARRAY_TYPED_RPC_PARAMS` registry | Works around psycopg2 function resolution for `UUID[]` params |
| `require_permission` is ANY-of | Matches how officer roles overlap; document it |
| Chapter-signup limiter is in-process | Deliberate, marked `ponytail:` with an upgrade path |
| Voiding a partially paid invoice forgives the whole face and leaves the payment as credit | Simplest consistent rule; document it |
| Roll call permits partial success | Officer marks 40 people; one failure should not undo 39 |
| Commitment history = append-only log + mutable current row | Standard pattern |
| v2 verify allocates oldest-first, ignoring the submission's `invoice_id` | Defensible accounting policy, but the UI must say so (see finding on this) |
| `login_attempts` has RLS and zero policies | Effectively "nobody but the owner", which is the intent |
| Dry-run SMS parents are `sent` while children are `simulated` | Lets the UI show the blast happened without hitting Twilio |
| Transactional email ignores SMS consent | Consent is an SMS-law concept |
| `is_officer` = any role except member | Correct for audience selection; wrong as an authority check (finding) |
| Query builder inlines the string `now()` as SQL `NOW()` | Small, contained convenience |

## 11 · Recommended project conventions

**In short:** the strongest existing code already defines the conventions. Write them down and stop the competing ones.

| Concern | Make official (dominant, strongest code) | Retire |
|---|---|---|
| Multi-row or trust-boundary writes | One plpgsql RPC: chapter guard, idempotency key, audit row, ledger row if money (`tr_*`, `tk_*`, `ev_*`) | Python sequences of autocommitted statements (`update_event`, `create_task`, onboarding, check-in) |
| Money | BIGINT cents in DB, `Money` in Python, `formatMoney`/`dollarsToCents` in TS | `NUMERIC` columns; `Decimal→float` in `_serialize` |
| Authority | `require_permission(*keys)` dependency, `can(key)` in the SPA | `members.role`, `LEGACY_ROLE_COMPAT`, `isOfficer`, inline `has_permission` |
| Identity equality | Normalise IDs to `str` at the platform boundary once | `str(a) == str(b)` sprinkled per call site |
| Tenant scope | Session `chapter_id` passed into an RPC that re-checks every referenced row | Trusting RLS |
| Idempotency | `UNIQUE(chapter_id, operation, key)` plus a payload hash | Client-chosen keys without hash or expiry |
| Invoice status and "owed" | `tr_refresh_invoice_status`; one remaining-cents helper for standing, reminders, dashboards | `tr_verify_payment` v1; `status='unpaid'` filters |
| Errors | Named domain exceptions mapped to fixed HTTP messages (events, initiatives) | `HTTPException(…, f"{exc}")` |
| Time | Timestamptz everywhere; one chapter timezone; one parser | Naive `date`+`time` combined with `tzinfo=UTC`; inline ISO slicing in adapters |
| Notifications | Enqueue inside the RPC transaction (as `an_send_announcement_sms` does); deliver only from the cron drain | Inline `dispatch_send`; post-commit `enqueue` that swallows errors |
| Configuration | Typed `Settings`; generate `.env.example` from it | Reading `os.environ`; nine dead env names |
| Frontend data | Domain hooks + pure adapters; toast after `await` | Optimistic toast before the request; client-local "ledgers" |
| Frontend forms and validation | Pure `lib/*.ts` validators returning `{valid, error}` | Inline `onSubmit` guards with toasts |
| Frontend permissions | `can(permissions, key)` | `isOfficer`, `isOfficerView` (57 sites) |
| Tests | Real DB fixtures with per-test chapters; dependency-override clients; name tests by invariant | `FakeSb`; patching `recompute_member_balance`; AST-only tests |
| Imports | Absolute `api.*` imports (346 vs 15 relative) | Cross-domain imports of private helpers |
| Naming | `snake_case` Python, `tr_/ev_/at_/tk_` RPC prefixes, `domain:verb` permission keys | `sb` for the DB client (call it `db`) |
| Directory shape | `api/<domain>/{api,services,core,auth.py}` as a menu, not a mandate | `db/` per domain, `repositories/` |
| Logging | Named loggers with request id, chapter id, outbox id via a filter | Bare `logger.warning` without correlation |
| Route paths | Frozen; new collection routes without trailing slash | Mixed trailing slashes |
## 12 · Remediation plan

**In short:** write ten tests, then fix authority and the standing/balance readers (all small), then close the autocommit pattern, then delete the parallel paths. Nothing here needs a rewrite.

### Phase 0 — safety net (before any refactor)

| Test to add | Guards |
|---|---|
| Revoking `officer` via `POST /api/rbac/revoke` removes `roles:assign` from `/me/permissions` | F-022 |
| Officer cannot assign `admin`; treasurer cannot assign `president` | F-023 |
| Roster CSV with `treasury_viewer` yields `members.role='member'` | F-006 |
| Adjustment where `member_id == officer_id` is rejected; self-verify rejected | F-027 |
| Standing: partially paid fine still counts; today's 20:00 event not missed at 09:00; fines count with zero past events | F-024, F-002, F-015 |
| Excuse approval leaves `member_finance_accounts` equal to `BalanceEngine` | F-028 |
| Same outbox row cannot be delivered by inline send and cron drain | F-017, F-019 |
| Link and phone check-in write an `audit_logs` row and void nothing silently | F-004, F-036 |
| Migration content checksum: CI fails if an applied file's hash changes | F-016 |
| One test per Phase-1 RPC change, run against the real DB, no `FakeSb` | all |

Prerequisites: none. Files: `tests/rbac/`, `tests/memberadmin/`, `tests/treasury/`, `tests/cron/`, `.github/workflows/ci.yml`. Blast radius: none (tests only).

### Phase 1 — P1 correctness, security, data integrity

| Order | Items | Files | Must not change | Blast radius |
|---|---|---|---|---|
| 1 | **Authority**: F-023 add a grant ceiling in `rbac_assign_role` (caller must hold the role or a superset); F-022 stop unioning `LEGACY_ROLE_COMPAT` once every `members.role='officer'` has a `member_roles` row (one backfill migration), or have revoke also clear the column; F-006 import writes `role='member'` unless `role_key='officer'` | `migrations/NNNN`, `api/rbac/core/policy.py`, `api/rbac/services/permissions.py`, `0157` successor | permission keys, `/me/permissions` shape | every permission check; run the full suite |
| 2 | **Self-dealing**: F-027 reject `p_actor_id = member_id` in `tr_create_adjustment`, `tr_verify_payment`, `tr_verify_payment_v2` | 3 RPC replacements | RPC signatures | verify/adjust routes |
| 3 | **Standing inputs**: F-024 count remaining cents (`amount − allocations`) not `status='unpaid'`; F-015 remove the early return; F-002 compare `date + time` to now | `api/memberadmin/core/engagement.py` | `derive_standing` signature (ADR-0004) | standing, scores, reminders |
| 4 | **Balance readers**: F-028 recompute in `at_review_excuse` (call the engine from Python right after, or write through in SQL) and have reports recompute before summing | `api/treasury/services/reports.py`, `api/attendance/services/excuses.py` | cache table shape | dashboards |
| 5 | **Verify paths**: F-029 route `POST …/verify` to v2 and retire `tr_verify_payment`; F-030 decide refund semantics (reopen the invoice or expose a balance payment in the SPA) | `api/treasury/api/payments.py:57-70`, `0052` successor | ledger entry types | payments UI |
| 6 | **Auth**: F-005 mark all unused codes used on password set and bump `token_version` on redeem; F-037 stop putting the code in the payload (render at send time from a hash-less short-lived table, or purge failed rows on expiry); F-007 arm the guard on any non-local run (`ENV`, not `VERCEL_ENV`) | `api/auth/api/auth.py`, `api/auth/notifications.py`, `api/config.py`, `api/index.py` | login/redeem responses | all logins |
| 7 | **Finance UI**: F-014 wire the four handlers to `POST /api/treasury/{invoices,payments/submissions,adjustments}` or remove the modal kinds | `greekos/src/hooks/useFinance.ts`, `FinanceModule.tsx` | API paths | finance tab |
| 8 | **Notifications**: F-017 delete inline `dispatch_send`, let the cron drain be the only sender; F-019 write `sending → sent` with the provider message id in one statement after the call and make the provider call idempotent by `dedup_key`; F-013 make the cooldown an insert-with-unique | `api/announcements/services/sms.py`, `api/cron/services/outbox_drain.py`, `api/events/services/notifications.py` | outbox row shape, claim RPC | every message |
| 9 | **Excuse/fine**: F-004 `at_set_attendance excused` voids the fine like `at_review_excuse`; add `UNIQUE (chapter_id, member_id, source_event_id) WHERE kind='fine' AND status<>'cancelled'` | `0146` successor | attendance route | fines |
| 10 | **IDs**: F-026 normalise UUIDs to `str` in `_exec_select` once; delete per-site `str()` | `api/platform/postgres.py:217-275` | nothing visible | every SELECT (run full suite) |
| 11 | **Tasks**: F-025 remove `status` from the generic PATCH; lifecycle only via `tk_*` | `api/tasks/api/schemas.py`, `tasks.py` | job routes | jobs UI |
| 12 | **Sessions**: F-003 resolve link→session by explicit id, fail closed on ambiguity | `api/attendance/services/checkin_links.py:88-133` | `/c/{code}` | check-in |
| 13 | **Prod**: F-010 generate `Prod/` from `LocalDev/` in CI (or point Vercel at `LocalDev/`), record prod migration state, populate `PROD_PROJECT_REFS` with a checksum guard (F-016) | `Prod/`, `scripts/`, `.github/workflows/` | live URLs | deploy |
| 14 | F-008 `REVOKE ALL ON ALL TABLES FROM anon, authenticated` + confirm the Data API is off | one migration | nothing | none if Data API is off |

### Phase 2 — P1 structural

- **F-011 autocommit.** Introduce `with db.transaction():` in `postgres.py` (one connection, `autocommit=False`, commit on exit) and wrap `update_event`, `create_task`, onboarding, roster import, check-in. Or move each into an RPC. Tests from Phase 0 first. Blast radius: every service; do it domain by domain.
- **F-012 event delete.** Replace hard delete with `status='cancelled'`; attendance and fines keep their history.
- **F-021 outbox enqueue.** Enqueue inside the RPC that produces the event (as `an_send_announcement_sms` already does); on the Python path, re-raise anything that is not the dedup unique violation.
- **F-031 balance source.** Either make `big_ledger` the source (rebuild becomes the engine) or drop the shadow-ledger claim from the docs and keep `rebuild.py` as a drift alarm that runs on a schedule.

### Phase 3 — consolidate competing patterns

F-053 retire the operations template engine (0003) or migrate it onto `tasks`; F-059 delete the legacy `process-event` fine path; F-060 store event start as `timestamptz` with a chapter timezone; F-032 make the UI say "applied to oldest first" or honour `invoice_id`; F-033 cache permissions per request; F-044 collapse the startup fan-out (one `/api/bootstrap` or per-tab loading); F-056/F-057 batch the 2N and 8-per-fine loops; adopt the conventions in §11 (one error mapper, one ID normaliser, one time parser, `can()` only).

### Phase 4 — delete obsolete and duplicate code

F-071 `AuditLogger`, `LedgerWriter`, `idempotency_operation`, `Page`, `select_orphaned_proofs`; F-066 scaffold deps and `react-example`; F-063 move templates out of `cron/core`; F-041 rewrite `CLAUDE.md`, `ARCHITECTURE.md`, `CODEMAP.md`, ADR-0002 from the real tree; `enqueueOutbox` stub and `selfcheck.ts`; plan-identifier comments (§8).

### Phase 5 — lower priority

F-001 honest copy for the command console and drop `@google/genai`; F-045 toast after `await`; F-046 health returns 503 on DB failure; F-051 cron heartbeat row; F-061/F-062 remount and a11y; F-064 one error mapper; F-065 uniform signup response + persisted limiter; F-067 request id in logs; F-069 test DB truncation job; F-070 payload hash on idempotency keys; F-052 replace `FakeSb` with real DB fixtures; F-009 one RLS test as a non-owner role.

## 13 · Ten things to fix before adding major features

1. Grant ceiling on role assignment (F-023).
2. One source of truth for roles; revoke must revoke (F-022, F-006).
3. Actor ≠ beneficiary in adjustments and verify (F-027).
4. Standing counts remaining cents and real event times (F-024, F-015, F-002).
5. Balance readers never trust the cache without a recompute (F-028).
6. One verify path (F-029) and a decision on refunds (F-030).
7. Finance tab writes to the server or loses the buttons (F-014).
8. One sender for the outbox, sent-state written with the provider id (F-017, F-019).
9. A transaction helper, applied to the five known half-apply paths (F-011).
10. `Prod/` built from `LocalDev/`, migration state recorded, checksum guard (F-010, F-016).

## 14 · Do NOT refactor right now

| Leave alone | Why |
|---|---|
| The `tr_*` RPC family and `payment_allocations` | Correct, tested, atomic. Add guards inside them; do not move logic out |
| `BalanceEngine` formula | The formula is right; the readers are wrong. Fix readers (F-028) before touching the engine |
| Outbox claim protocol (`0155`) | Correct under concurrency; the bugs are around it, not in it |
| `Money`, `formatMoney`, `dollarsToCents` and the strict money regex | Specified and tested; F-049 was refuted |
| Router include order, `_ARRAY_TYPED_RPC_PARAMS`, the three events `notifications.py` files | Deliberate, documented, load-bearing |
| `fines_legacy.py` URL surface and the `unpaid_invoices` name | Renames with no behaviour change; the frontend freezes the paths |
| The PostgREST-shaped query builder | Replace it deliberately in Phase 2 with the transaction helper, not opportunistically |
| `is_officer` as an audience predicate | Right for SMS audiences; only wrong as an authority check |
| Roll-call partial success, commitment log + current row, dry-run SMS parents | Reasonable choices (§10) |

## 15 · Final assessment

**In short:** about two thirds of the risk is correctness and security, one third maintainability. The codebase needs targeted refactoring and consolidation, not a rewrite. Start with authority and the standing/balance readers; the treasury RPC core is the healthiest part.

| Question | Answer |
|---|---|
| Risk split | ~65% correctness/security/financial (roles, standing, balance readers, half-applied writes, outbox delivery), ~35% maintainability (parallel paths, docs, frontend structure, tests) |
| Rewrite, targeted refactor, consolidation, or conventions? | Targeted refactor (Phase 1, mostly small changes) + consolidation (Phases 3–4) + written conventions (§11). No subsystem needs a rewrite. |
| First subsystem to work on | RBAC/authority, because every other fix is enforced through it. Then `memberadmin` standing and the treasury readers. |
| Healthiest subsystem | Treasury RPC core and the outbox claim protocol; auth basics close behind. |

**If a senior team inherited this tomorrow:** they would trust the database functions and the tests that hit them; distrust anything that reads `members.role`, any dashboard number, the Finance tab's buttons, the `Prod/` folder and the architecture docs; and they would, before building anything new, collapse authority to one source with a ceiling, make standing and balances read live data, put a transaction around every multi-step write, and make production reproducible from the repo. That is four to six weeks of focused work, most of it small changes guarded by the ten tests in Phase 0.
## Appendix A · Invariants

**In short:** 23 rules the code relies on. Seven are strong, eleven partial, four weak, one absent. Money and auth are strong; attendance, fines, standing and roles are where the rules are assumed rather than enforced.

| Invariant | Enforced at | Assumed at | Bypass | DB-level | Tests | Strength |
|---|---|---|---|---|---|---|
| Money is integer cents | `Money`, treasury BIGINT + CHECKs | standing thresholds, SPA formatters | `events.fine_amount` NUMERIC, `ev_create_event` NUMERIC param, `Decimal→float` in `_serialize`, generic invoice route accepts any `kind=fine` amount | treasury tables only | `test_v1_fines.py` | partial |
| `big_ledger` and `audit_logs` append-only | triggers | all `tr_*` | none in production (Python writers are test-only) | yes | `test_chunk0_foundations.py` | **strong** |
| Balance = f(operational tables); ledger is a shadow | `BalanceEngine`, recompute on read | dashboards, SMS audience, CSV read the cache | `at_review_excuse` voids without recompute; crash between RPC and recompute; reallocation ignored | none | `test_chunkB_balance.py` | partial |
| One verified payment per submission | `FOR UPDATE` + `UNIQUE(submission_id)` | notify only when created | none | yes | `test_chunkC_payments.py` | **strong** |
| One fine per required event and member, ≥24 h after start, never for excused/present | `issue_fines` only (racy read) | standing, fine lists | no unique index; `process_event_fines` with null key; generic invoice route; check-in does not void | none | `test_v1_fines.py` happy path | **weak** |
| Invoice status = allocation state | `tr_refresh_invoice_status` (v2) | standing, void guard | `tr_verify_payment` v1 writes status directly; standing ignores `partially_paid` | CHECK on vocabulary only | one writer each | partial |
| Member belongs to one chapter | `chapter_id NOT NULL`, email unique | login, JWT | phone not unique; Twilio START/STOP updates every row with that phone | yes | login tests | **strong** (phone is not an identifier) |
| Chapter A never touches chapter B | Python filters + RPC guards | every list route | owner connection bypasses RLS; 12 tables have no RLS; no `FORCE` | policies exist, unenforced | tenant-guard RPC tests | partial |
| Roles imply permissions only via the catalog | `get_member_permissions` | `require_permission`, `can()` | `rbac_revoke_role` leaves `members.role=officer`; union restores the grant | no trigger keeps column and table aligned | none for revoke | **weak** |
| "Officer" has one definition | `is_officer` = any role but member | SMS audience, feed | permission checks use keys; `treasury_viewer` is an "officer" for audience only | none | audience tests | partial |
| `token_version` invalidates sessions | `get_current_user`, `au_set_password` | client-side logout | reset path bumps in a second autocommit; redeem does not bump | column only | `test_tokens.py` | **strong** |
| Setup code single-use and expiring | `au_consume_setup_code` conditional UPDATE | redeem route | several live codes can coexist; hash check outside the RPC | conditional UPDATE | `test_invite_setup_codes.py` | **strong** |
| Invited member cannot log in by email alone | login requires `status=active` | invite flow | none (redeem issues a token, which is the code working) | status CHECK | login tests | **strong** |
| One attendance row per event+member; transitions guarded | `UNIQUE(event_id, member_id)`, `at_set_attendance` | roster, standing | link/phone check-in upsert without touching excuses or writing audit; `data[0]` on duplicate phones | unique only | RPC rollback test | partial |
| Excused and fined cannot both stand | `at_review_excuse` voids one unpaid fine | 0146 comment | `at_set_attendance excused` does not void; later fines not cleared; partially paid skipped | excuse uniqueness only | one test | **weak** |
| Standing derives only from unpaid fines and unexcused absences | `derive_standing` signature | ADR-0004, firewall test | inputs are wrong: same-day future events count as missed; partial payments vanish | none | firewall + rules tests | partial |
| Task has ≤1 parent; commitments ≤ capacity | CHECK, `tk_commit_task` lock + count, partial unique | jobs UI | `create_task` sets capacity in a second statement (lowers only) | yes | tasks tests | **strong** |
| Security swap transitions closed | status CHECK, partial unique, update/delete triggers, `ev_accept_swap` | swap UI | direct UPDATE to a terminal status (no app path) | yes | `test_security.py` | **strong** |
| Outbox row sent at most once; SMS only with consent | `UNIQUE(dedup_key)`, claim protocol, consent predicate | ADR-0005 wording | delivery is at-least-once; inline `dispatch_send` and cron both send pending rows | unique + status CHECK | drain tests; no double-sender test | partial |
| Idempotency keys make retries no-ops | `UNIQUE(chapter_id, operation, key)` | clients | no payload hash; no expiry; null keys skip; v1/v2 operation names differ | unique only | treasury idempotency tests | partial |
| Every trust-boundary mutation is an RPC with an audit row | money, roles, attendance override, excuse review, tasks, swaps, announcements, invite | CLAUDE.md hard rule | ~25 direct Python writers (check-in, excuses submit, setup codes, evidence, consent, outbox status, sessions, links, recruits, usage, …) | per-function, no general trigger | per-RPC assertions | partial |
| Migrations never edited after apply | filename tracking only | CLAUDE.md | 0147 and 0149 committed twice with behaviour changes; nothing detects content drift | filename PK | none | **absent** |
| Production cannot boot with dev defaults | `production_config_violations` | deploy | only when `VERCEL_ENV` set; does not reject the demo `DATABASE_URL`; `BASE_URL`, `PLATFORM_SECRET` unchecked | none | `test_production_guard.py` | partial |
## Appendix B · Method

**In short:** three external coding agents did the reading; the lead session did the grouping, the cross-checks and the writing. Every P0/P1 and every confirmed P2 was handed to a different vendor with the instruction "assume this is wrong".

| Stage | What | Who | Output |
|---|---|---|---|
| 0 | Baseline checks: 1030 backend tests, frontend lint/tests/build, npm audit | lead | Appendix C.1 |
| 1 | Six mechanical inventories (routes, DB, code shape, tests, frontend, config), spot-checked 3 rows each | Gemini 3.6 Flash via Antigravity | JSON tables |
| 2 | Eight deep audits, one area each, starting from the inventories | see below | findings JSON |
| 3 | 59 adversarial refutes on a different vendor than the finder; lead eye-check of every kept P1 | Codex ↔ Gemini Pro ↔ Grok | verdict JSON |
| 4 | Dedupe by root cause, write | lead | this report |

| Dig | Agent / model | Minutes | Findings |
|---|---|---|---|
| D1-security | cursor / grok-4.7-xhigh | 17 | 9 |
| D2-money | cursor / grok-4.7-xhigh | 18 | 10 |
| D3-workflows | codex / gpt-5.6-sol high | 14 | 15 |
| D4-comms-ops | codex / gpt-5.6-sol high | 14 | 18 |
| D5-frontend | agy / Gemini 3.1 Pro (High) | 5 | 9 |
| D6-tests | agy / Gemini 3.1 Pro (High) | 4 | 4 |
| D7-shape | codex / gpt-5.6-sol high | 18 | 12 |
| D8-invariants | cursor / grok-4.7-xhigh | 19 | 11 |

<details><summary>▸ What was not read (from the auditors' own coverage notes)</summary>

- **D1-security:** did not re-file those items. Read in full: auth routes and notifications, dependencies, config, index boot guard, observability, chapters auth/onboarding/routes, cron auth and routes, twilio inbound, check-in page and check-in link service, attendance and excuses routes, payments routes and most of payments service, balances and reports routes, fines_legacy routes, members routes, all rbac Python,
- **D2-money:** not read S1 result.json. Sampled S2 result.json: its coverage note claims a live pg_catalog dump, but column lists contradict the SQL and a passing suite (member_finance_accounts.balance_cents, finance_adjustments.amount_cents, payment_allocations and invoice_line_items lacking chapter_id, event_types.default_fine_amount). Those rows were not used. Replayed all 64 migration files for CREATE TABLE,
- **D3-workflows:** Did not run pytest, node tests, TypeScript, migrations, seeds, servers, or deployments; conclusions are static code/DDL traces against the lead's established runtime facts and baseline. No command was sandbox-blocked. Final `git status --short` exactly matched the pre-audit state: modified `docs/superpowers/plans/2026-09-30-forensic-audit/02-stage1-sweep.md` and untracked `../Analysis.md`, `tests/
- **D4-comms-ops:** did not restate its confirmed production-copy or serverless batch-timeout findings. Read both requested stage-1 inventory JSON files in full. Fully traced the mandated outbox, cron, email, SMS, consent, announcements, auth/event/treasury/task producers, relevant migrations, frontend outbox hook/module, focused cron/announcement/event/auth/memberadmin tests, configuration, deployment manifests, wor
- **D5-frontend:** did not execute the frontend unit tests individually or run full e2e testing. I relied on manual source review for timezone and form behavior.
- **D6-tests:** Read 25 test files directly via `view_file`. Encountered `invalid_args` when trying to read non-existent frontend test files (`adapters.test.ts` and `outbox-channel.test.ts`), so I read other frontend and backend test files instead to satisfy the 24 file requirement. Connection to the sandbox server failed, so I relied entirely on file reading to perform the audit.
- **D7-shape:** not read every line of all 65 migrations, every test file, every large React render body, or every archived/plan document; migration bodies and tests were followed selectively for retained findings. I did not connect to either database, inspect real production data, invoke external providers, or run tests because the audit was read-only and the supplied baseline already covered the suites. Query c
- **D8-invariants:** not read 0006, 0101, 0110, 0142, or 0158 end to end, the contribution package beyond the firewall import check, or greekos modules beyond api.ts verify URL. S1 and S4 inventories were summarized by key, not read line by line. S2 constraint text was checked against SQL and is wrong in places: attendance has no status column, invoice and payment statuses are lowercase, task commitment status is acti

</details>

Rule violations by the auditors: several refuters wrote throwaway probe tests and scratch scripts into `LocalDev/` and two edited a `conftest.py` to prove a finding. The lead saved the diffs as evidence (`stage3/violations.md` in the run archive) and reverted every change; the repository was clean before the report was written. One Gemini refute hit a quota limit and was rerun on Cursor.

Known limits: no test was run against a non-owner database role, so nothing here proves or disproves the RLS policies; the production database was never queried; `Prod/` was compared to `LocalDev/` by diff, not by deploying it; the frontend was audited by reading, not by running it in a browser.

## Appendix C · Lead-session baseline and reference (merged from `Analysis.md`, 2026-10-05)

**In short:** the lead session's pre-audit notes, folded in so there is one document. C.1–C.3 are reference material for anyone fixing findings (paste C.2 into agent prompts so they do not re-derive it). C.4 lists the eight things the notes found that never became a finding card; they carry `R-` IDs. C.5 maps every item of the old notes to where it lives now. Where the notes and the report disagree on a count (handlers 125 vs 140, `isOfficer` 29 vs 57, tables without RLS 13 vs 12, fetch wrappers 4 vs 5), the report's number is the later, inventory-backed one.

### C.1 Baseline checks (run 2026-09-29/30, commit `c89c716`)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python3 -m pytest` from `LocalDev/` against the Supabase demo DB | **1030 passed, 0 failed**, 647 s. 2 warnings: Starlette TestClient/httpx deprecation; duplicate OpenAPI operation id for `cron_drain_outbox` (GET+POST on one handler, `api/cron/api/cron.py:38`). Slowest: `tests/cron/test_drain_outbox.py::test_drain_route_returns_counts` 7.4 s. |
| Frontend typecheck | `npm run lint` (tsc --noEmit) in `greekos/` | pass |
| Frontend unit tests | `npm test` (node:test) | 86 passed |
| Frontend build | `npm run build` | pass, 482 kB JS / 44 kB CSS |
| Frontend audit | `npm audit --omit=dev` | 0 vulnerabilities |
| Python env | installed fastapi **0.133.1** | `LocalDev/requirements.txt` pins **0.141.1** (dependabot bump not installed locally); `Prod/requirements.txt` pins 0.133.1 |
| Linters | none configured | no ruff/mypy/black/pyproject anywhere; CI has no Python lint step |

Sizes: `api/` 15,295 lines Python (125 route handlers), `migrations/` 65 files / 10,124 lines,
`tests/` 87 files / 17,943 lines (844 `def test_`, 1030 collected), `greekos/src` 12,618 lines
TS/TSX, 10 TODO/FIXME markers in code.

### C.2 Established runtime facts (verified in code)

Paths are relative to `LocalDev/`.

1. **One DB path, autocommit per statement.** `api/platform/postgres.py:170-187` and `:536-545`
   set `conn.autocommit = True` on every execute; only plpgsql RPCs are atomic. Any Python
   sequence of `.insert/.update/.delete` is non-atomic.
2. **RLS is not enforced at runtime.** App connects as `postgres.<ref>` (table owner). Policy
   helpers (`treasury_request_member_id`, `rbac_request_chapter_id`, `treasury_claim_sub_uuid`)
   read `request.jwt.claims`, which nothing sets. ADR-0002 admits this. Tenant isolation =
   Python `.eq("chapter_id", …)` filters + RPC-body guards.
3. **Correction 2026-10-05:** the uuid part of this fact is wrong. A live SELECT returns id columns as `str` (psycopg2 2.9.11, no `register_uuid` anywhere in the repo), so `user["id"]` is a string and F-026's str-vs-UUID mechanism does not occur at runtime. SELECT rows do still differ from RETURNING rows for `Decimal` and date/time values. Original text follows.
   **Type inconsistency of ids.** `_exec_select` returns raw psycopg2 types (uuid.UUID,
   Decimal, datetime) — it never calls `_serialize` (`postgres.py:218-276`); INSERT/UPDATE/UPSERT
   RETURNING rows go through `_serialize` (`:437-455`: UUID→str, **Decimal→float**,
   date/time→isoformat). RPC results are jsonb (string ids). `a == b` between ids from different
   sources can be silently False; much code wraps `str()` inconsistently.
4. **Identifier interpolation.** Column names in `.eq/.in_/.order/.select` and `on_conflict`
   are interpolated unescaped into SQL (`postgres.py:222-256, 337-351, 370-387, 391-429`);
   values are parameterised; RPC names/params regex-validated (`:523-528`). No user-controlled
   column name was found yet (not fully swept).
5. **Auth.** HS256 JWT `sub`=member id, `iss/aud=guildos`, 7-day exp, `ver` claim vs
   `members.token_version` (`api/auth/api/auth.py:52-65`, `postgres.py:548-584`,
   `api/dependencies.py:6-39`). No refresh; logout is client-side only. `authorization.replace("Bearer ", "")`.
   Login/redeem rate limits count `login_attempts` failures per email (10/15 min) and per
   rightmost-trusted `X-Forwarded-For` (20/15 min) (`auth.py:164-198`); the attempt insert is
   swallowed on error. `dev-login` 404s when deployed or when `DEV_AUTH_BYPASS` is false.
6. **Authorization.** `require_permission(*keys)` is ANY-of; `get_member_permissions` = 2
   queries (`member_roles`, then `role_permissions`) unioned with legacy `members.role` via
   `LEGACY_ROLE_COMPAT` (`api/rbac/services/permissions.py`). Ownership scoping only for
   `tasks:complete → tasks:review` (`api/rbac/core/policy.py:21-44`). Several routes use inline
   `has_permission` instead (balances, dashboards, evidence, fines list, excuses list).
7. **Money.** `Money` rejects floats (`api/treasury/core/money.py`); BIGINT cents tables; legacy
   NUMERIC(10,2) columns remain: `events.fine_amount`, `fines.amount`,
   `event_types.default_fine_amount` (0003), `ev_create_event.p_fine_amount NUMERIC`
   (0101/0141). `FineToInvoice(fine_amount=event["fine_amount"])` converts once in
   `fine_processor.py:79`.
8. **Balances** (`api/treasury/core/balance.py`) are computed from operational tables only
   (`unpaid_invoices` status != cancelled, `verified_payments`, active `finance_adjustments`,
   active `refunds`), never from `big_ledger`; `member_finance_accounts` is a cache that
   `get_member_balance` recomputes before every read (`services/balance.py:8-33`). `big_ledger`
   is a shadow whose drift is only reported by `core/rebuild.py`.
9. **Seed credentials.** `scripts/seed.py:34` sets `DEMO_PASSWORD = "demo-officer-pw"` for every
   seeded member (documented in `greekos/README.md`); seed is guarded by `require_demo`.
   `scripts/set_officer_password.py` has no demo/prod guard.
10. **Config.** `Settings` fields not documented in `.env.example`: `PLATFORM_SECRET`,
    `TRUSTED_PROXY_HOPS`. Local `.env` carries 9 names `Settings` ignores (`extra="ignore"`):
    `ESCALATION_DELAY_MINUTES`, `FEATURE_SECRETARY_COMMS`, `FEATURE_VP_OPERATIONS`,
    `MESSAGE_WEBHOOK_SECRET`, `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SUPABASE_ANON_KEY`,
    `SUPABASE_DB_URL`(used by tests), `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`.
11. **Async handlers, sync I/O.** All routes are `async def` and call psycopg2 directly;
    only `/api/health` and the cron drain use `asyncio.to_thread`. 14 `async def` service
    functions await nothing.

### C.3 Key RPC and trigger behaviour, read in full

- `tr_create_invoice` (0080 version) and `tr_create_invoice_v2` (0120): idempotency by
  `(chapter_id, operation, key)` with no payload hash; member∈chapter guard; ledger + audit
  rows; `p_actor_id` may be NULL.
- `tr_bulk_create_invoices` (0158 is live): per-item member guard, `due_at`, idempotent by key.
- `tr_submit_payment` (0080): invoice must belong to the member; rejects cancelled/paid.
- `tr_verify_payment` (0031) and `tr_verify_payment_v2` (0124): `FOR UPDATE` on the submission,
  idempotent replay returns `_created:false`; rejected → raises; v2 allocates oldest-first via
  `payment_allocations` (append-only, reversal rows), `tr_refresh_invoice_status` recomputes
  unpaid/partially_paid/paid; `UNIQUE(submission_id)` backstop. Service then recomputes the
  balance cache and enqueues a notification in Python (not in the transaction).
- `tr_reject_payment` (0031): approved → raises; rejected → idempotent.
- `tr_void_invoice` (0122): reason required; allowed on unpaid/partially_paid; writes
  `CANCEL_INVOICE` ledger row; status vocabulary is `cancelled` (no `void` value exists).
- `tr_reallocate_payment` (0124): reversal rows + new set, total ≤ verified amount, member match.
- `at_set_attendance` (0146): validates event/member/actor in chapter; excused path deletes and
  re-inserts the excuse as approved; present/absent upsert; audit row; idempotency key is always
  NULL from the route (`api/attendance/api/attendance.py:197-205`).
- `at_review_excuse` (0146): approve voids one matching **unpaid** fine invoice via
  `tr_void_invoice`; no state-transition guard (re-review allowed).
- `outbox_claim_batch` (0155): `FOR UPDATE SKIP LOCKED` claim → `sending`, requeues claims older
  than 15 min, fails rows with `attempts >= 5`; `attempts` increments on **claim**, not on
  delivery.
- `ch_create_chapter` / `ch_import_roster` (0156): SECURITY DEFINER, `search_path=public`;
  chapter+officer(+member_roles) atomic; roster rows atomic; **setup codes are issued afterwards
  in Python** (`api/chapters/services/onboarding.py:74-84, 175-182`).
- `au_invite_member` (0161) writes member + setup code atomically (the fix the onboarding paths
  did not get).
- Triggers: `big_ledger_no_delete`, `big_ledger_limited_update` (active→invalidated only),
  `audit_logs_immutable`, append-only guards on receipts/allocations/evidence/line items,
  `fines_frozen`, `at_derive_chapter_id` on attendance/excuses/checkin_links (0146),
  `outbox_pin_sms_channel`.

### C.4 Residual items (in the notes, no finding card)

| ID | Sev | Item | Where | Fix with |
|---|---|---|---|---|
| R-01 | 🔵 P3 | No Python linter or type-checker anywhere; CI has no Python lint step | no `ruff`/`mypy`/`pyproject` in the repo; `.github/workflows/ci.yml` | F-040 (CI and bootstrap) |
| R-02 | 🔵 P3 | Duplicate OpenAPI operation id: `cron_drain_outbox` serves GET and POST from one handler | `api/cron/api/cron.py:38` | F-051 (cron) |
| R-03 | 🔵 P3 latent | `_serialize` converts `Decimal` to `float` on every RETURNING row, against the "no float money" rule. Only the legacy NUMERIC fine columns can hit it today | `api/platform/postgres.py:447-448` | F-026 (same function family) |
| R-04 | 🔵 P3 latent | Column names in `.eq/.in_/.order/.select` and `on_conflict` are interpolated into SQL unescaped. §5 confirmed no request-controlled identifier reaches the builder today | `api/platform/postgres.py:222-256, 337-351, 370-387, 391-429` | F-039 (query builder); validate with the regex RPC names already use (`:523-528`) |
| R-05 | 🟡 P2 likely, unverified | The outbox is one global FIFO with no per-chapter fairness; a burst from the unauthenticated signup can delay every chapter's mail | `migrations/0155_outbox_claim.sql:84-125`, `api/cron/services/outbox_drain.py:55, 284-315` | F-018, F-065 |
| R-06 | 🔵 P3 | Tenant-guard rejections surface as opaque 500s; cross-chapter responses are inconsistent (404 / 403 / zeros) | `api/initiatives/services/initiatives.py:317-325`, `api/initiatives/api/initiatives.py:24-35` | F-064 (one error mapper) |
| R-07 | 🔵 P3 | `.env.example` lacks `PLATFORM_SECRET` and `TRUSTED_PROXY_HOPS`; the local `.env` carries nine names `Settings` ignores (`ESCALATION_DELAY_MINUTES`, `FEATURE_SECRETARY_COMMS`, `FEATURE_VP_OPERATIONS`, `MESSAGE_WEBHOOK_SECRET`, `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`) | `api/config.py`, `.env.example` | F-007 (config) |
| R-08 | ⚪ P4 | Untracked local residue contradicting "no `db/` per domain": `api/*/db/__pycache__`, `api/standing/api/__pycache__`, `LocalDev/fratos/{.next,node_modules}` | working tree only, not in git | F-071 (dead code sweep) |

Also noted, no action of its own: all routes are `async def` over sync psycopg2 and 14 `async def` service functions await nothing (part of F-044); `authorization.replace("Bearer ", "")` and client-side-only logout (`token_version` is the real revocation); the seed sets one documented demo password for every member, behind `require_demo` (the unguarded script is F-020).

### C.5 Where each item of the old notes went

| `Analysis.md` item | Now |
|---|---|
| §1 baseline checks | C.1 |
| §2 architecture map | §2 |
| §3 runtime facts | C.2 |
| §4 RPC behaviour | C.3 |
| §5.1 Finance actions never persist | F-014 |
| §5.2 Prod not reproducible | F-010, F-016 |
| §5.3 Drain vs serverless timeout | F-018 |
| §5.4 Onboarding half-applies | F-011 |
| §5.5 Naive event times as UTC | F-060 |
| §5.6 Legacy process-event fines | F-059 |
| §5.7 Unauthenticated phone check-in | F-036 |
| §5.8 Signup enumeration and spam | F-065 |
| §5.9 Raw exception text | F-064 |
| §5.10 Decimal→float | R-03 |
| §5.11 Idempotency keys | F-070 |
| §5.12 Balance cache recomputed per read | F-056 |
| §5.13 Docs vs reality | F-041 |
| §5.14 Import cycle | F-063 |
| §5.15 Optimistic UI | F-045 |
| §5.16 Untracked residue | R-08 |
| §6 anon/authenticated DML | F-008 |
| §6 no grant ceiling | F-023, F-006 |
| §6 self-verify, self-credit | F-027 |
| §6 members can read the live check-in code | F-036 |
| §6 task-status ownership fails open | F-025, F-026 |
| §6 outbox has no tenant fairness | R-05 |
| §6 cross-tenant email disclosure | F-065, F-064 |
| §6 Twilio START across chapters | F-068 |
| §6 tenant-guard 500s | R-06 |
| §7 patterns worth preserving | §9 |
| §8 not yet covered | done by stages 1–3 (Appendix B) |
