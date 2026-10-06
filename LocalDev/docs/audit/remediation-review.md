# Remediation review — 2026-10-06

After all 18 remediation streams were merged to `main`, one Opus reviewer per stream checked
its work against the code on `main` (read-only, adversarial). This file collects every
reviewer's findings. **Nothing here is fixed yet.**

Severity: **P0** money/security/data loss · **P1** wrong behaviour · **P2** missing guard or
weak test · **P3** style or minor.

## Summary

- **0 P0, 3 P1, 27 P2, 41 P3.**
- **16 streams have issues; 2 are clean (05 and 15, minor notes only).**
- **These audit findings are only partly fixed:**
  - F-045: two roster actions still fake success.
  - F-064: three error handlers still leak database text.
  - R-06: removing a chair still returns a 500.
  - F-042: security swap acceptance has no lock.
  - F-054: co-chairs can still be set at creation.
  - F-041: some docs are still stale.
- **Found by two reviewers each:**
  - Self check-in doesn't void an open fine (10, 09).
  - The balances CSV mixes live and cached numbers (08, 09).
  - The event-type race inside `update_event` causes a 500 (01, 11).
- **Full suite on the wave 4 merge:** not finished when this was written (it was at 86%, no
  failures shown).

### The three P1s

1. **06:** "Add member" and "change standing" in the Roster show a success toast but never
   call the server. The change is gone on reload.
2. **18:** a `Prod/` sync would delete `Prod/fratos/vercel.json`, which keeps git deploys off
   for the fraternity-os project. Auto-deploys would start again.
3. **02:** a chapter created with `scripts/provision_chapter.py`, the path for the first
   production chapters, gets no admin. Nobody can ever grant or revoke admin or president
   there.

### Needs your decision

- **13:** preview deploys no longer refuse a localhost `FRONTEND_URL`. The plan's own test
  allows it. Keep it, or restore the old rule?
- **17:** `LocalDev/CLAUDE.md` still says "production `DATABASE_URL` points at the demo".
  Your earlier note says production has real data. Which is true?
- **04:** should the inactive-member guard (D12) also cover event supervisors?

| Stream | Verdict | P1 | P2 | P3 | Not fully fixed |
|---|---|---|---|---|---|
| 01 db client | issues | 0 | 1 | 1 | — |
| 02 authority | issues | 1 | 1 | 2 | — |
| 03 treasury RPCs | issues | 0 | 3 | 2 | — |
| 04 DB guards | issues | 0 | 2 | 3 | F-042, F-054 |
| 05 finance tab | clean | 0 | 0 | 3 | — |
| 06 frontend shell | issues | 1 | 1 | 1 | F-045 |
| 07 CI tooling | issues | 0 | 2 | 2 | — |
| 08 standing/balance readers | issues | 0 | 2 | 1 | — |
| 09 fines pipeline | issues | 0 | 3 | 1 | — |
| 10 check-in | issues | 0 | 2 | 3 | — |
| 11 events/tasks | issues | 0 | 1 | 3 | — |
| 12 outbox delivery | issues | 0 | 2 | 3 | — |
| 13 auth/config | issues | 0 | 1 | 0 | — |
| 14 outbox ops | issues | 0 | 0 | 4 | — |
| 15 startup/events UI | clean | 0 | 0 | 1 | — |
| 16 sweep | issues | 0 | 2 | 2 | F-064, R-06 |
| 17 docs | issues | 0 | 3 | 7 | F-041 |
| 18 prod & ops | issues | 1 | 1 | 2 | — |

---

## 01 — DB client

- **P2** `update_event` runs `resolve_event_type_id(tx)` inside a transaction. Its helpers
  catch a unique violation on `event_types`, which aborts the transaction, so a race gives a
  500. `ignore_conflict` can't target the expression index `(chapter_id, lower(name))`.
  `api/events/services/events.py:57-62, 85-98, 715-719`.
  - **Fix:** allow a no-target `ON CONFLICT DO NOTHING` in `insert()`, or use a savepoint.
- **P3** `transaction()`'s `finally` uses `tx` before it is assigned if
  `conn.autocommit = False` raises. The `UnboundLocalError` hides the real error and leaks a
  pool slot. `api/platform/postgres.py:654-674`.

## 02 — Authority

- **P1** `scripts/provision_chapter.py:282-291` grants only `officer`, with no `admin` row
  (breaks D8). **Fix:** also insert the admin role; update the script header.
- **P2** `test_admin_revoke_takes_the_chapter_lock` is flaky.
  `tests/rbac/test_authority.py:153-172`.
  - **Why:** `SET`/`RESET lock_timeout` on an autocommit cursor through the transaction
    pooler (6543) can land on a different server connection. The setting can then leak into
    the shared pool.
  - **Fix:** use a non-autocommit connection with `SET LOCAL`.
- **P3** The admin check runs before the chapter lock, so an admin who was just demoted can
  still finish a revoke. The last-admin guard still holds.
  `migrations/0203_rbac_revoke_admin_lock.sql:30-41`.
- **P3** Comments still say the legacy `members.role` grants permissions:
  - `announcements/services/sms.py:112-113`
  - `announcements/services/announcements.py:126-127`
  - `rbac/__init__.py:10-12`
  - `members/api/members.py:94-96`

## 03 — Treasury RPCs

- **P2** A refund can reopen a paid invoice while the money really sits as credit on a
  cancelled invoice. `migrations/0167_refund_reopens_invoice.sql:68-83`.
  - **Why:** the reversal loop ignores invoice status. Allocations created in the same
    `now()` are ordered by uuid.
  - **Fix:** reverse allocations on cancelled invoices first, then newest first.
- **P2** The `refunds_freeze` trigger doesn't freeze `member_id`, but balances add up refunds
  by `member_id`. One UPDATE can move a refund to another member.
  `migrations/0168_freeze_money_columns.sql:38`, `api/treasury/core/balance.py:128-136`.
- **P2** `POST /payments/record` with a reused Idempotency-Key and a changed body returns a
  500; it should be a 409. `api/treasury/api/payments.py:207-235`.
- **P3** Refund and verify can deadlock: they lock a member's invoices in opposite orders
  (0167 vs 0166).
- **P3** Some tests re-run the 0165 data block across the whole shared DB, not just their own
  chapter:
  - `tests/treasury/test_single_coverage.py:24-28, 73, 145-146`
  - `tests/treasury/test_chunkG_rebuild_hardening.py:283`

## 04 — DB guards

- **P2 (F-042 not fully fixed)** `ev_accept_security_swap` never takes the
  `ev_security:<event>` advisory lock, so concurrent calls can double-assign a member.
  `migrations/0175_inactive_member_guards.sql:200-272`.
- **P2 (F-054 not fully fixed)** `in_create_initiative` checks co-chairs only for being in
  the chapter, not for status, so an inactive or alumni member can become a chair.
  `migrations/0144_initiatives_v1.sql:103-123`.
- **P3** Event supervisors have no status check (`ev_create_event`, `ev_add_supervisor` in
  0141). Needs your decision: does D12 cover supervisors?
- **P3** `FOR UPDATE` on `initiatives` blocks unrelated child inserts; `FOR NO KEY UPDATE`
  would do. `migrations/0174_initiative_chair_locks.sql:20,84`.
- **P3** `test_assign_security_takes_the_event_lock` failed once under shared-DB load and
  passed when run alone. Watch it.

## 05 — Finance tab (clean)

- **P3** The unused `Fragment` import is back in `greekos/src/App.tsx:1`. Lint doesn't catch
  it because `noUnusedLocals` is off.
- **P3** The event-fine dropdown lists events the server refuses until 24h after they start
  (the 422 does show inline). `greekos/src/lib/transaction.ts:179-180`.
- **P3** The Payments reference column maps `invoice_id`, which is always NULL, so it always
  shows "N/A". The officer's `proof_ref` is never shown. `greekos/src/adapters.ts:264`.

## 06 — Frontend shell

- **P1 (F-045 not fully fixed)** `handleAddMember` and `handleUpdateStanding` only update
  local state and show a success toast; they never call the server.
  `greekos/src/hooks/useRoster.ts:36, 41`.
- **P2** After a failed startup load, `backendDown` stays true for good. A later write that
  succeeds is then shown as "Not saved: the server is unreachable". The user retries and
  creates a duplicate, for example a second SMS blast. `sync.test.ts` asserts this wrong
  behaviour. `greekos/src/lib/sync.ts:25`, `greekos/src/hooks/useBackend.ts:37-51`.
- **P3** A network failure mid-session is reported as "the server refused the change"; it
  should say the server is unreachable. `greekos/src/lib/sync.ts:37-39`.

## 07 — CI tooling

- **P2** `migrate_db.py --prod` changes production before the operator confirms, and before
  it refuses an unknown history. `scripts/migrate_db.py:94, 179-185`.
  - **Why:** it adds the checksum column and backfills it, committing both, ahead of the
    prompt at 197-205.
  - **Fix:** do a read-only history check first; do the ALTER and backfill after
    confirmation.
- **P2** The dependency stamp hashes only `requirements.txt`. A new venv or a different
  `python3` never gets its dependencies installed, and `pip` may belong to another
  interpreter. `local-dev-scripts/scripts/local-dev.sh:204-210`.
- **P3** `tests/test_migrate_history.py` tests only the helpers. The `main()` exits (an
  edited migration, an unknown production history) are untested.
- **P3** `CLAUDE.md` doesn't say "run `migration_checksums.py --update` after adding a
  migration".

## 08 — Standing and balance readers

- **P2** The `member_balances` CSV makes only `outstanding` live. Owed, paid, current and
  `recomputed_at` come from the cache, so rows contradict themselves and members with no
  cache row export blanks. `api/treasury/services/reports.py:361-376`.
- **P2** The per-member event breakdown marks future required events "absent" (a sibling of
  F-002). `api/memberadmin/services/member_detail.py:28-35, 87-91`.
- **P3** `_past_event_ids` uses the server's `date.today()`, not the chapter timezone.
  `api/tasks/services/commitments.py:115`.

## 09 — Fines pipeline

- **P2** A fine can still land on someone excused or marked present if the two happen at the
  same moment (breaks D20).
  - **Why:** `tr_issue_event_fines` trusts an absence list built in Python, and
    `at_set_attendance` / `at_review_excuse` don't take the event lock.
  - **Where:** `migrations/0201:26`, `migrations/0198`, `api/treasury/api/fines_legacy.py:191-205`.
  - **Fix:** re-check attendance and excuses inside the RPC; take the event lock in both
    functions.
- **P2** Self check-in (`at_checkin_self`, 0178) doesn't void an open fine. Same as 10.
- **P2** Issuing fines no longer refreshes the balance cache, but the CSV still reads cached
  figures. Same root cause as 08.
- **P3** The atomicity test calls the RPC directly, so it proves nothing about the route.
  `tests/treasury/test_v1_fines.py:296-306`.

## 10 — Check-in

- **P2** `at_checkin_self` never calls `at_void_open_fines`. A fine issued 24h after the
  start, followed by a door-code check-in, leaves the member present but still owing.
  `migrations/0178_checkin_guards.sql:24-33`.
- **P2** `logger.exception` became `logger.error` with no traceback, so a database fault
  leaves no trace. `api/attendance/services/checkin_links.py:213`.
- **P3** Two officers opening a check-in session at once get a raw 500, not a 409.
  `api/attendance/services/sessions.py:40`.
- **P3** The F-003 card's "same session gate on active-link reads" was left out of scope.
  Closed sessions' codes still show as live:
  - `get_active_link_for_event`
  - the bulk read in `events.py:550-575`
  - `list_active_links_for_chapter`
- **P3** A link rotated while a session bound to the old link is open isn't governed by that
  session's close time. `checkin_links.py:126-131, 160`.

## 11 — Events and tasks

- **P2** Cancelling an event leaves its pending security swaps pending and its job claims
  active. The existing security-cancel path in 0145 handles both.
  `migrations/0181_event_cancel.sql:37-38`.
- **P3** The event-type race inside `update_event` gives a 500 (same as 01).
- **P3** `_rpc_http_error`'s fallback turns any unexpected error (for example the database
  being down) into a 400 that carries raw text. `api/tasks/api/tasks.py:108-113`,
  `api/tasks/api/jobs.py:56`.
- **P3** A cancelled event still accepts new check-in links, sessions and excuses:
  - `events.py:261-268`
  - `attendance/services/sessions.py:25-33`
  - `excuses.py:22-28`

## 12 — Outbox delivery

- **P2** The 5-attempt cap can never trigger, because claim +1 and the refund −1 keep pending
  rows at 0 attempts. A row that crashes the worker before the provider stamp is retried
  forever and blocks the front of the queue. `migrations/0200_outbox_ops.sql:9-17` (from
  0186).
- **P2** If closing a row as `sent` fails after the provider call succeeded, the row becomes
  `failed` with database error text. Retry then clears the provider stamp, so the message is
  sent twice. `api/cron/services/outbox_drain.py:303-307`.
- **P3** When the time budget runs out, claimed but unsent rows wait in `sending` for 15+
  minutes. `outbox_drain.py:343-345`.
- **P3** `test_inline_dispatch_skips_rows_the_cron_already_claimed` would pass with the fix
  reverted.
- **P3** `api/cron/core/__init__.py` is still tracked; the plan said to remove that
  directory.

## 13 — Auth, config and onboarding

- **P2** Preview deploys, and runs with no `VERCEL_ENV`/`APP_ENV`, no longer refuse a
  localhost `FRONTEND_URL`, which is the CORS allowlist. The plan's own test allows it.
  Needs your decision. `api/index.py:108-115`.

## 14 — Outbox operations

- **P3** On a fresh instance with the database down, `/api/health` returns a 500, not a 503,
  because `get_db()` raises before the health check runs. `api/index.py:217`.
- **P3** A docstring still says failed code rows keep their code for Retry, which is false
  under D21. `api/auth/notifications.py:10-12`.
- **P3** The UI shows a Retry button on SETUP_CODE/RESET_CODE rows, which always returns
  409. `greekos/src/lib/consent.ts:37`, `greekos/src/components/OutboxModule.tsx:189`.
- **P3** The oldest-pending-age test may read another chapter's row.
  `tests/cron/test_heartbeats.py:36-45`.

## 15 — Startup and events UI (clean)

- **P3** If refreshing an event's details fails (for example the event was just cancelled),
  the fresh task list is thrown away too. `greekos/src/lib/app-data.ts:25-31` uses
  `Promise.all`; use `allSettled`.

## 16 — Sweep

- **P2 (F-064 not fully fixed)** Three more error mappers still return raw database text:
  - `api/tasks/api/commitments.py:21-33`
  - `api/tasks/api/jobs.py:43-56`
  - `api/events/api/security.py:41-53`
- **P2 (R-06 not fully fixed)** `DELETE /api/initiatives/{id}/chairs/{non-chair}` still
  returns a 500, because "is not a chair" isn't mapped.
  `api/initiatives/services/initiatives.py:373`.
- **P3** `TreasuryMessage` is now dead code. `api/treasury/api/schemas.py:11`.
- **P3** Roster import still says which emails belong to another chapter.
  `api/chapters/services/onboarding.py:170`.

## 17 — Docs

- **P2 (F-041 not fully fixed)** Two docs claim a `Prod/` drift check runs in CI (it doesn't
  yet), and give the path `scripts/build_prod.sh` (it's
  `LocalDev/scripts/build_prod.sh`). Root `CLAUDE.md:4-5`, `LocalDev/docs/ARCHITECTURE.md:37`.
- **P2** `ARCHITECTURE.md:10` calls `FrontendConventions.md` the frontend spec, but that file
  describes the archived Next.js app.
- **P2** Stale claims about the old frontend and the old fine path:
  - `service-map.md:8, 19` says to check `fratos/lib/api-client.ts`, and that fines go
    through `FineToInvoice` (float to cents).
  - ARCHITECTURE §3 claims `Money.from_numeric` is used by the old fines import.
- **P3** `CONTEXT.md:118-120` defines "Heartbeat" wrongly, and the "top role" entry is
  missing.
- **P3** `CODEMAP.md` mentions a Sidebar "chapter switcher" that doesn't exist, and leaves
  out `api/platform/errors.py` and `outbox.py`.
- **P3** Some rows in the `LocalDev/CLAUDE.md` Conventions table describe things the code
  doesn't do (lines 213, 216-217, 219-220).
- **P3** Stale statements in `ARCHITECTURE.md`:
  - JWT `sub` is described as `auth_id`; it is `member_id`.
  - New tables are said to take writes through "service-role RPCs"; the app connects as the
    table owner.
  - "RPCs for all multi-row writes" ignores `transaction()`.
- **P3** `TREASURY_ARCHITECTURE.md` §3, §10 and §11 are missing the new treasury RPCs,
  routes and migrations.
- **P3** "RLS on 43 tables" is stale; it is now 45.
- **P3** Two historical claims need fixing:
  - The "prod `DATABASE_URL` points at demo" note: needs your decision.
  - ADR-0002's historical path should be `api/db.py`.

## 18 — Prod and ops

- **P1** `build_prod.sh` keeps only top-level files, so `rsync --delete` would remove the
  tracked `Prod/fratos/vercel.json` (`deploymentEnabled=false`). `LocalDev/scripts/build_prod.sh:6, 75`.
- **P2** `test_build_prod` only passes while `Prod/` has drifted, so it will fail after the
  sync. Create drift in the temp copy instead. `tests/test_build_prod.py:25`.
- **P3** `--exclude='.env*'` drops the tracked `greekos/.env.example`, so a sync would delete
  `Prod/fratos/.env.example`.
- **P3** Each purge batch locks writes on every table with a trigger. The runbook should say
  to run it only when no tests are running.

---

Raw notes: `archive/audit-remediation-2026-10/final-review.md` (gitignored).
