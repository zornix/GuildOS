# GTM Larp Checklist

Where GuildOS is pretending to be shippable and isn't. Audited 2026-08-01
against `LocalDev/` on `main` (c6d94d7), assuming the frontend is done.

The premise of the audit: if we released v1 tomorrow, what breaks or embarrasses
us? The answer is not missing features. The core domains — treasury, events,
initiatives, tasks, RBAC — are real, RPC-backed, tenant-guarded, and tested. The
gaps are that **three things the product promises (log in securely, check in,
get notified) do not work in production**, plus we have no way to onboard a
chapter or migrate the prod database.

"Larp" = a surface that reports success while doing nothing. Those are called
out explicitly below because they are worse than missing features: a missing
feature is a roadmap item, a fake success toast is a trust incident.

---

## Tier 1 — Cannot ship (security & correctness)

### 1.1 Member login requires no password

`api/auth/api/auth.py:47` — the password branch runs only when
`member["role"] == "officer" and member.get("password_hash")`. Every
`role="member"` account authenticates on **email alone** and receives a 30-day
HS256 JWT with full member access to the chapter's roster, finances, standing,
and attendance.

Compounding:
- Officers with no `password_hash` also get a grace login
  (`auth.py:62-64`, sets `password_setup_required`), so the first person to
  guess an un-onboarded officer's email claims the account and then calls
  `POST /api/auth/set-password` (`auth.py:93-107`) to lock everyone else out.
  Known and deferred in `docs/imp-one-gate.md:28-31`.
- `POST /api/auth/invite` (`auth.py:123-150`) creates `status="active"` members
  with no verification — i.e. it manufactures claimable passwordless accounts.
- Tokens (`auth.py:16-21`): 30-day expiry, no `jti`, no `iss`/`aud`, no
  revocation list. Logout is `localStorage.removeItem`
  (`fratos/lib/api-client.ts:96`); the token stays valid for 30 days after.

Fix is already designed but unbuilt: `docs/imp-one-gate.md` D2 ("everyone uses a
password"). Its migration `0146_authority_one_gate.sql` does not exist —
`migrations/` stops at `0146_attendance_tenant_guards.sql`.

### 1.2 Phone check-in is broken end to end

The flagship anti-cheat surface has never worked as shipped.

| File:line | Behavior |
|---|---|
| `api/attendance/api/checkin_page.py:116` | submit enabled only at **exactly 10** digits |
| `api/attendance/api/checkin_page.py:122` | submit handler hard-gates on 10 digits |
| `api/attendance/api/checkin_page.py:100` | `formatPhone` `.slice(0, 10)` — input cannot hold more |
| `api/attendance/api/schemas.py:46-47` | `PhoneCheckIn` rejects anything but **9** digits |

Every phone check-in returns 422 and the page shows "Check-in failed". No test
covers the path (`tests/attendance/` holds only `test_tenant_guards.py`;
`tests/services_scaffold/test_route_registration.py:18` asserts only that the
route exists).

**Underlying decision to make, not just a digit fix:** check-in matches bare
normalized digits against raw `members.phone` (`api/attendance/api/attendance.py:84`,
seeded 9-digit at `scripts/seed.py:47-54`), while Twilio requires E.164
(`api/announcements/services/sms.py:256`). The two features demand incompatible
storage for one column and there is no normalization layer. Populate phones for
SMS and check-in stops matching; populate for check-in and SMS fails.

### 1.3 Stored XSS on the public check-in page

`api/attendance/api/checkin_page.py:39,73,74,146` interpolate `event['title']`
and `event['location']` into an f-string HTML/JS template with no escaping. Event
titles are officer-controlled; the page is served unauthenticated at
`/c/{short_code}` on the production origin.

### 1.4 The production boot guard has a hole shaped like our own `.env.example`

`api/index.py:20-41` refuses to boot production when `JWT_SECRET ==
"local-dev-secret"`, `DATABASE_URL` is unset, or `DEV_AUTH_BYPASS` is truthy.
Good idea; the coverage is thin.

- **The exact-match string is wrong.** `api/config.py:10` defaults to
  `"local-dev-secret"`, but `.env.example:43` instructs operators to set
  `JWT_SECRET=local-dev-secret-key-change-in-prod`. Copy the example to prod and
  the guard **passes** with a secret that is published in the repo. Switch to a
  prefix/entropy check.
- **No length or entropy floor** — `JWT_SECRET="x"` boots.
- **Preview deploys are deliberately unguarded** (`api/index.py:35-36`,
  `tests/config/test_production_guard.py:62-64`). Vercel preview URLs are public
  and inherit env vars; a preview with `DEV_AUTH_BYPASS=1` against the prod
  pooler is a complete auth bypass on a live URL. In prod `use_local_db` is
  True, so `DEV_AUTH_BYPASS` is the *only* thing gating
  `POST /api/auth/dev-login` (`auth.py:68-90`).
- Unchecked in prod: `MESSAGE_WEBHOOK_SECRET` (`.env.example:66`, currently dead
  config but goes live with the outbox worker), `CRON_SECRET`, `FRONTEND_URL`
  (default `http://localhost:3000`), `SUPABASE_SERVICE_ROLE_KEY` presence.

### 1.5 RLS is inert in production — app-level tenant isolation only

25 migrations enable RLS and 41 `CREATE POLICY` statements exist, all keyed on
`rbac_request_chapter_id()` (`migrations/0082_rbac_foundation_tables.sql:55-70`)
→ `treasury_claim_sub_uuid()` (`migrations/0006_treasury_foundation_rls_rpc.sql:3-20`)
→ `current_setting('request.jwt.claim.sub', true)`. That GUC is set only by
PostgREST. Under ADR-0002 the prod path is direct Postgres, which never calls
`set_config` (zero hits for `set_config|SET LOCAL|request.jwt` in `api/`) and
connects as the table-owning pooler role with no `FORCE ROW LEVEL SECURITY`.

This matches CLAUDE.md's stated position (RPC bodies are the runtime guard), and
`.env.example:9` says so — but the 41 policies read like a safety net that is
not deployed. Anyone reasoning about defense-in-depth here will be wrong.

Related doc drift: `CLAUDE.md:95` still says Supabase client = prod, PostgresClient
= local. The boot guard now *requires* `DATABASE_URL` in prod, so prod runs the
PostgresClient path and `_LocalAuth` (`api/postgres_client.py:526-548`) is the
production JWT verifier. Security rests entirely on `JWT_SECRET` — see 1.4.

### 1.6 Cross-tenant hole: check-in link deletion

`api/events/api/events.py:285` — `DELETE /api/events/{event_id}/checkin-link`
calls `deactivate_checkin_link(event_id)` with no `chapter_id` scope, unlike its
`POST` sibling at `events.py:262-281`. The service
(`api/attendance/services/checkin_links.py:142-149`) filters on `event_id` only.
Any officer of any chapter can kill any other chapter's live check-in link.

Adjacent smell: `list_active_links_for_chapter`
(`api/attendance/services/checkin_links.py:113-129`) queries every active link
across all chapters and filters by `chapter_id` in Python. Output is correct;
the query is cross-tenant and one refactor from a leak.

### 1.7 Announcements leak drafts to every member

`api/announcements/api/announcements.py:26-27` — `GET /api/announcements/`
returns drafts and all audiences to any authenticated member. A president's
unsent draft is readable chapter-wide today.

---

## Tier 2 — The app lies about notifications

### 2.1 `message_outbox` has no drain

Table at `migrations/0070_treasury_message_outbox.sql:14`. There is no worker,
no cron, and no drain function anywhere in the repo (zero hits for
`drain|worker|process_outbox|dispatch_outbox|flush_outbox`).

The only dispatcher is `dispatch_send` (`api/announcements/services/sms.py:196`),
called **inline inside the HTTP request** and scoped to a single send-log row by
`target_table`/`target_id` (`sms.py:209-216`). Every outbox row with any other
`target_table` is unreachable by any code path:

| Producer | Event types | `target_table` | Dispatcher |
|---|---|---|---|
| `api/treasury/notifications.py:105,118,131,144` | `INVOICE_ISSUED`, `PAYMENT_APPROVED`, `PAYMENT_REJECTED`, `REFUND_ISSUED` | `unpaid_invoices`, `payment_submissions`, `refunds` | none |
| `migrations/0142_jobs_v1_lifecycle.sql:333,347,410,428,502,511` | `JOB_REPORTED/APPROVED/REJECTED` | `tasks` | none |
| `migrations/0144_initiatives_v1.sql:571,585,600` | `JOB_REPORTED` | `tasks` | none |
| `migrations/0145_security_swaps_v1.sql:271,278,363,450,457,574,591,654,661` | `SECURITY_ASSIGNED/REMOVED/SWAP_REQUESTED/ACCEPTED/DECLINED` | `tasks` | none |

Documented as intentional (`api/treasury/notifications.py:5-7,18-19`, "out of
scope for V1") — but no API route or UI surfaces the outbox either (zero hits
for `outbox` in `api/*/api/` or `fratos/`). So a member is never told their
payment was approved, their job was rejected, or that they caught a security
shift — not by SMS, not in-app. This is the largest single launch blocker in
Tier 2, and Phase 2 of `docs/planned.md` already scopes the fix.

### 2.2 Success is reported for sends that never happened (larp)

- `MESSAGE_DELIVERY_MODE` defaults to `dry_run` in three places
  (`api/announcements/services/sms.py:61`, `api/events/services/notifications.py:66`,
  `api/treasury/notifications.py:31`), and dry-run marks outbox rows
  **`status='sent'`** with no network call (`sms.py:218-223`). The exec SMS log
  (`GET /api/announcements/sms-log`) therefore renders a clean delivery history
  of messages that were never delivered.
- `MESSAGE_DELIVERY_MODE` is read from `os.environ`, not `api/config.py`, so it
  is outside the settings surface and outside the production boot guard.
- An unrecognized value returns early (`sms.py:227-228`), leaving rows `pending`
  forever with no error — one typo in a Vercel env var silently disables all SMS.
- `POST /api/memberadmin/remind/{member_id}` (`api/memberadmin/api/scores.py:23-55`)
  returns `{"message": "Reminder queued"}` after touching no queue, no outbox,
  no provider. Its own docstring says "Placeholder". Officer sees a success
  toast; member hears nothing.

### 2.3 The one working send path breaks on first real use

- **Env var name mismatch:** `sms.py:276` reads `os.environ["TWILIO_FROM_NUMBER"]`;
  `.env.example:63` defines `TWILIO_FROM_PHONE`.
- The resulting `KeyError` is swallowed by a bare `except Exception: status = "failed"`
  with no logging (`sms.py:258-259`). Flipping to `twilio` marks every row
  `failed` and tells nobody.
- Prerequisite still open: A2P 10DLC campaign registration
  (`sms.py:21-22,269-271`). Unregistered traffic gets carrier-blocked. Long lead
  time — start before it blocks the launch (already flagged as decision #4 in
  `docs/planned.md`).

---

## Tier 3 — We cannot actually operate it

### 3.1 No way to onboard a chapter

No signup, no onboarding, no tenant provisioning (zero hits for
`signup|sign-up|onboarding|provision` in `api/` or `fratos/`). **No endpoint
writes to the `chapters` table at all** — the only `INSERT INTO chapters` is
`scripts/seed.py:201`, which first deletes the chapter (`seed.py:185`), and
`scripts/db_guard.py:79-92` refuses to let seed run anywhere but demo/localhost.
Onboarding a real chapter today is hand-written SQL.

### 3.2 No working production migration path

- `scripts/db_guard.py:29` — `PROD_PROJECT_REFS: frozenset = frozenset()` is
  still empty under a `HUMAN ACTION REQUIRED` banner (`db_guard.py:22-28`), so
  `npm run migrate:prod` refuses to run at all (`db_guard.py:99-104`).
- Nothing runs migrations on deploy: root `vercel.json` has no `buildCommand`,
  no `installCommand`, no build hook. Code ships ahead of schema by default.
- Forward-only, no down-migrations (`scripts/migrate_db.py`). The runner itself
  is good — lexical order, `schema_migrations` tracking (`:84`), per-file
  transaction with rollback (`:166-184`).
- No documented or tested backup/restore strategy (no hits for
  `backup|pg_dump|point-in-time|restore` in `docs/`, `scripts/`, `CLAUDE.md`).
  We are relying on whatever the Supabase plan defaults to.

### 3.3 No email, therefore no password reset

No `sendgrid`, `resend`, `smtp`, `mailgun`, `postmark`, or `ses` anywhere.
`SENDGRID_API_KEY`/`SENDGRID_FROM_EMAIL` (`.env.example:64-65`) are read by zero
code, as are `MESSAGE_WEBHOOK_SECRET` and `ESCALATION_DELAY_MINUTES`
(`.env.example:60,66`).

Consequences: no password reset flow exists at all (zero hits for
`reset.password|password_reset|forgot`). `POST /api/auth/set-password` requires
an already-valid session (`api/auth/api/auth.py:94`), so a locked-out officer
needs someone to run `scripts/set_officer_password.py` by hand against prod.
`POST /api/auth/invite` notifies nobody (see 1.1).

### 3.4 No error reporting, no rate limiting

- **Observability:** no `sentry-sdk` or any observability dep in
  `requirements.txt` (11 lines). One logger in the entire backend
  (`api/instrumentation/services/usage.py:9`). No `logging.basicConfig`, no
  exception handler, no request/correlation ID. `api/index.py:75` registers
  exactly one middleware (CORS). Unhandled exceptions become a default 500 whose
  traceback exists only in Vercel logs, unalerted. `/api/health`
  (`api/index.py:109` → `api/health_checks.py:30`) is a real DB ping that
  nothing polls.
- **Rate limiting: none anywhere.** No limiter dep, no middleware, no
  `fratos/middleware.ts`. Deferred explicitly in `docs/imp-tenant-guards.md:207`.
  So: `POST /api/auth/login` is an unauthenticated email-enumeration oracle
  (401 vs 403 `PASSWORD_REQUIRED` vs 200 — three distinguishable responses,
  `auth.py:42-43`); officer password brute-force is unbounded with no lockout;
  and `POST /api/attendance/checkin/{code}/phone` (unauthenticated by design)
  lets anyone holding a live link enumerate chapter phone numbers via 404-vs-200
  and check in arbitrary members.

### 3.5 CI does not gate anything

`.github/workflows/ci.yml:63` runs `bash deploy/verify-local.sh`, but
`LocalDev/deploy/` does not exist. The workflow cannot pass, so nothing gates
merges.

### 3.6 Cron is dead config and unauthenticated

- The crons block lives in `api/vercel.json:13-18`, which Vercel never reads —
  only the project-root `vercel.json` counts, and that one has no `crons` key.
  Nothing scheduled runs in production today.
- The single route `GET /api/cron/process-fines` (`api/cron/api/cron.py:6-17`)
  returns `{"status": "disabled"}` and has **no `CRON_SECRET` check** — no auth
  dependency of any kind. `CRON_SECRET` is declared at `api/config.py:17` and
  referenced by zero other lines, while `.env.example:49-52` and
  `api/config.py:15` both claim "empty → the endpoint returns 401". That claim
  is false, and the comment points at `api/routes/cron.py`, which no longer
  exists. Booby trap for the first real cron job — and Phase 2 needs one.

---

## Tier 4 — Decide, don't build

### 4.1 Cut two shells from the nav

Both are honest about being unimplemented, and both are in the nav with UI that
tells the user so.

- **NL controller / "Command"** (162 LOC): `api/nl_controller/services/commands.py:20-22`
  has no parser and hardcodes `proposed_actions = []`; `:60-63` approving a
  command executes nothing. Nav item at `fratos/config/navigation.ts:36`;
  `fratos/views/command.tsx:79` tells the user "nothing runs automatically".
- **Bylaws Q&A** (133 LOC): `api/bylaws/services/documents.py:41-53` —
  `query_bylaws` returns `{"status": "not_implemented"}`. Nav at
  `navigation.ts:35`; `fratos/views/bylaws.tsx:67` renders a question box that
  always comes back empty. **Bylaws CRUD is real — keep it, drop the Q&A box.**

Both are already on the frozen list in `docs/planned.md`. Freezing them but
shipping their nav entries is the larp.

### 4.2 Retire `require_officer` — it is a functional bug, not debt

`api/dependencies.py:46-49` is a raw `user["role"] != "officer"` string compare,
contradicting ADR-0003 stackable roles. `LEGACY_ROLE_COMPAT`
(`api/rbac/core/policy.py:15-18`) maps only `officer` and `member`, so a member
holding `president` or `treasurer` via `member_roles` — with `members.role` left
as `"member"` — is hard-403'd from all 12 remaining sites:

- `api/events/api/events.py:262` — create check-in link (**the core officer flow**)
- `api/events/api/events.py:285` — kill check-in link
- `api/attendance/api/checkin_links.py:10` — list active check-ins
- `api/memberadmin/api/scores.py:12,18,24` — engagement, member detail, remind
- `api/memberadmin/api/standing.py:10` — roster standing
- `api/treasury/api/fines_legacy.py:249,270` — fine processing, summary
- `api/auth/api/auth.py:124` — invites
- `api/members/api/members.py:25` — role updates (privilege escalation gated by a string compare)
- `api/tasks/api/operations.py:19` — template application

Also `api/members/api/members.py:27` still enforces binary
`role in ("officer","member")`, contradicting the stackable catalog at
`/api/rbac/roles`. Frontend mirrors the legacy gate:
`fratos/config/navigation.ts:40` (`OFFICER_ONLY`), consumed at
`fratos/components/layout/app-shell.tsx:44`, plus ~10 `user.role === "officer"`
branches in `fratos/views/*.tsx` (dashboard 22,41,46,71; fines 51,64; members 50;
events 48,101,171). Three authorization systems are live at once:
`require_permission` (37 sites), treasury `require_capability` (17),
`require_officer` (12). `docs/imp-one-gate.md` D1/D3 specify the deletion; none
of it has landed.

### 4.3 CORS and API surface

`api/index.py:75-81` is an explicit allowlist (right shape, not a wildcard), but
`http://localhost:3000` is hardcoded and allowlisted **in production** — gate it
on `not settings.is_production`. Exposure is limited because the token is a
`localStorage` bearer header (`fratos/lib/api-client.ts:114-118`), not a cookie.
Also: `/api/docs` and `/api/openapi.json` are public in prod
(`api/index.py:71-72`) — a full endpoint and schema map for anyone. No security
headers anywhere (`vercel.json` has no `headers` block; `fratos/next.config.ts`
is empty).

---

## Tier 5 — Smaller, but user-visible

- **Legacy `fines` table reads return null for every V1 fine.** The table has
  been frozen since `migrations/0012_fines_to_invoices_migration.sql` (see
  `api/treasury/api/fines_legacy.py:3`); fines are now `unpaid_invoices(kind='fine')`,
  which `api/memberadmin/core/engagement.py:89` uses correctly. But
  `api/memberadmin/services/member_detail.py:54-55` still queries `table("fines")`,
  so `GET /api/memberadmin/member/{id}` reports `fine_amount: null` for a member
  who owes money, and `api/memberadmin/api/scores.py:41-47` always returns
  `unpaid_count: 0`. Bonus: the legacy column is dollars (`amount`) while
  everything else is `amount_cents`.
- **Contribution ledger undercounts the two highest-effort actions.**
  `api/tasks/services/commitments.py:107-108` and
  `api/tasks/api/commitments.py:117-118` omit `events_organized` /
  `events_supervised`. Chapter-visible.
- **Deprecated supervisor route changed semantics silently.**
  `api/events/api/events.py:157` → `api/events/services/events.py:658`:
  `POST /{event_id}/supervisor` is marked DEPRECATED, still mounted, and now
  *adds* a co-supervisor instead of setting one. Callers expecting replace
  semantics accumulate supervisors.
- **Standing reason code with no consequence.**
  `api/memberadmin/core/standing_rules.py:9-12` — incomplete required tasks add
  a reason code but never shift the bucket, so a member with 10 blown tasks
  still reads `good_standing` while the UI shows the reason. `docs/planned.md`
  Phase 1 already removes `INCOMPLETE_REQUIRED_TASKS` per ADR-0004 — do it.
- **Attendance sessions are decoration.**
  `api/attendance/api/attendance.py:105-111` never stamps `session_id`, and
  `closes_at` (`api/attendance/services/sessions.py:66`) is never consulted by
  `validate_checkin_link` (`api/attendance/services/checkin_links.py:72-87`) —
  an officer's close time is unenforced; only the 10-minute link TTL applies.
- **Recruitment stage changes write no audit log.**
  `api/recruitment/services/pipeline.py:4-6` bypasses the `rc_*` RPC despite the
  action being registered in migration 0082.
- **Opaque 500 on check-in code generation.**
  `api/attendance/services/checkin_links.py:49-69` — bare `except Exception:
  continue` treats any DB error as a code collision, then raises bare `Exception`.
- **Usage analytics will degrade.** `api/instrumentation/services/usage.py:44-64`
  fetches every matching row and counts in Python, unbounded. Also carries
  committed stream-of-consciousness comments at `:44-49`.
- **Test coverage is lopsided.** 51 test files, 29 covering events + treasury.
  Zero backend tests for `bylaws`, `recruitment`, `nl_controller`, `auth`,
  `members`, and the phone check-in path.

---

## Stale docs found during the audit

- `api/attendance/CONFORM_TODO.md` — items 1 and 2 are already done
  (`api/routes/`, `api/services/`, `api/models/` are empty; the schemas already
  moved). Three items remain genuinely open: the last `require_officer` holdout
  at `api/attendance/api/checkin_links.py:3,10`, unstamped `session_id`, and
  unenforced `closes_at`.
- `api/events/__init__.py:3-5` claims handlers live in `api/routes/events.py`
  and points at an `api/events/CONFORM_TODO.md` that does not exist.
- `api/attendance/services/signals.py:3` references `api/services/fine_processor.py`
  (now `api/treasury/services/fine_processor.py`).
- `CLAUDE.md:95` describes the prod/local client split backwards post-ADR-0002
  (see 1.5).
- `.env.example` is gitignored (`.gitignore:141`) and untracked, so new
  operators have no source-controlled config reference.

---

## Suggested sequence

Minimum for one real chapter, roughly in order:

1. **1.1** password for every member (`imp-one-gate.md` D2) — hardest, start now.
2. **1.2** phone check-in digits + a phone-storage normalization decision.
3. **2.1** outbox drain worker + the cron auth it needs (3.6) — `planned.md` Phase 2.
4. **1.4** tighten the boot guard (prefix/entropy check, cover preview).
5. **1.3 / 1.6 / 1.7** XSS escape, chapter scope on link deletion, announcements filter.
6. **3.2** fill `PROD_PROJECT_REFS`, get a working prod migration path.
7. **2.2 / 2.3** stop reporting success for dry-run sends; fix the Twilio env name; start A2P 10DLC.
8. **3.3 / 3.4** password reset, login rate limiting, Sentry.
9. **3.1** chapter provisioning (can be a vetted script for the first few chapters).
10. **4.1 / 4.2** cut the two shell nav items; retire `require_officer`.

Parallel and cheap: **3.5** (fix or delete the broken CI step) and the stale-doc
cleanup, so the next audit starts from truth.
