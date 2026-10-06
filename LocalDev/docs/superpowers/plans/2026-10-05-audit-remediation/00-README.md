# Audit remediation — directing guide

> **For agentic workers:** you were given this file plus ONE numbered plan. Read "Rules for every agent" and "What to hand back" here, then execute your plan task by task. Everything else in this file is background you may consult. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `LocalDev/docs/audit/2026-09-30-forensic-audit.md` (68 findings `F-…`, 8 residuals `R-…` in Appendix C.4). Each plan names the cards it implements; read those cards before you start.
**Status (2026-10-06, end of session 3):** waves 1–3 and stream 18 code tasks merged to `main` and green; wave 4 (16, 17) and stream 18 tasks 2-apply and 4 next. **Read `HANDOFF.md` next** (state, carry-overs, model rules: Opus for every Claude agent, prefer Gemini 3.8 Flash / GPT-6 Sol).
**Written:** 2026-10-05 by the orchestrating session (Claude Fable 5.1). Product decisions were made by the user that day and are recorded under "Decisions". They are not open for re-litigation; if one turns out to be impossible, stop and report.

## Streams

| # | Plan | Wave | Agent (CLI · model · effort) | Branch | Findings | Migrations |
|---|---|---|---|---|---|---|
| 01 | `01-db-client.md` | 1 | Claude · Opus 5.5 | `fix/audit-01-db-client` | F-011 (helper), F-021, F-026, F-039, R-03, R-04 | none |
| 02 | `02-authority.md` | 1 | Cursor · Grok 4.7 · medium | `fix/audit-02-authority` | F-022, F-023, F-006, F-033, F-052 | 0162–0164, 0203 |
| 03 | `03-treasury-rpcs.md` | 1 | Claude · Opus 5.5 | `fix/audit-03-treasury-rpcs` | F-029, F-030, F-031, F-032, F-058, F-070, F-014 (server) | 0165–0170, 0204, 0205 |
| 04 | `04-db-guards.md` | 1 | Cursor · Grok 4.7 · medium | `fix/audit-04-db-guards` | F-042, F-047, F-054, F-008, F-009, F-048 | 0171–0175 |
| 05 | `05-finance-tab.md` | 1 | Claude · Fable 5.1 | `fix/audit-05-finance-tab` | F-014, F-061, F-070 (client) | none |
| 06 | `06-frontend-shell.md` | 1 | Claude · Fable 5.1 | `fix/audit-06-frontend-shell` | F-045, F-062, F-001, F-066 | none |
| 07 | `07-ci-tooling.md` | 1 | Antigravity · Gemini 3.8 Flash · medium | `fix/audit-07-ci-tooling` | F-016, F-040, R-01 | none |
| 08 | `08-standing-balance-readers.md` | 2 | Codex · GPT-6 Luna · medium | `fix/audit-08-standing-readers` | F-024, F-015, F-002, F-028, F-056 | 0176–0177 |
| 10 | `10-check-in.md` | 2 | Codex · GPT-6 Luna · medium | `fix/audit-10-check-in` | F-036, F-003, F-011 (check-in) | 0178–0180 |
| 11 | `11-events-tasks.md` | 2 | Codex · GPT-6 Luna · medium | `fix/audit-11-events-tasks` | F-012, F-011 (events, tasks), F-025, F-043, F-053 | 0181–0185 |
| 12 | `12-outbox-delivery.md` | 2 | Cursor · Grok 4.7 · medium | `fix/audit-12-outbox-delivery` | F-063, F-017, F-019, F-018, F-013, F-034 | 0186–0190 |
| 13 | `13-auth-config-onboarding.md` | 2 | Codex · GPT-6 Luna · medium | `fix/audit-13-auth-config` | F-005, F-007, F-020, F-065, R-07, F-011 (onboarding) | 0191–0194 |
| 09 | `09-fines-pipeline.md` | 3 | Cursor · Grok 4.7 · medium | `fix/audit-09-fines-pipeline` | F-004, F-057, F-059, F-060, F-024 (summary) | 0195–0199 |
| 14 | `14-outbox-ops.md` | 3 | Cursor · Grok 4.7 · medium | `fix/audit-14-outbox-ops` | F-037, F-050, F-051, F-046, F-067, R-02 | 0200–0202 |
| 15 | `15-startup-and-events-ui.md` | 3 | Claude · Fable 5.1 | `fix/audit-15-startup` | F-044 | none |
| 18 | `18-prod-and-ops.md` | 3 + end | orchestrator | `fix/audit-18-prod-ops` | F-010, F-069, R-08, human halves of F-016/F-038/F-008 | none |
| 16 | `16-sweep.md` | 4 | Antigravity · Gemini 3.8 Flash · medium | `fix/audit-16-sweep` | F-064, R-06, F-071 | none |
| 17 | `17-docs.md` | 4 | Antigravity · Gemini 3.8 Flash · medium | `fix/audit-17-docs` | F-041, docs for F-031/F-038/F-068/R-05 | none |

Why each model: Opus gets the two streams where a mistake touches every query or every dollar. Grok gets SQL, locking and security work (it found the top findings during the audit). Luna gets well-specified Python service edits. Gemini Flash gets mechanical work with exact instructions. Fable does the frontend and all verification. No finding is fixed by the vendor that will review it.

**Waves.** A wave starts only after the previous wave is merged to `main` and the full suite is green. Inside a wave every stream runs in parallel in its own worktree. Wave 2 needs 01 (transactions), 02 (authority) and 03 (coverage) merged; wave 3 needs 08, 10, 11, 12, 13; wave 4 needs everything.

**Not fixed, by decision:** F-027 (D2), F-068 (D16), R-05 (D17). **Not reproduced:** F-026 (D23).

## Rules for every agent

1. **Reproduce first.** Every fix starts with a test that fails on your untouched branch for the reason the finding describes. If you cannot make it fail, do not change production code for that finding: mark it `NOT_REPRODUCED` in your report, say what you tried, keep any useful regression test, and move on. One audit finding has already turned out to be wrong this way.
2. **Stay in your lane.** Change only the files your plan lists under "Allowed files". If a fix seems to need another file, stop that task and report it as `BLOCKED` with the file and the reason. Never edit `Prod/`, `archive/`, another stream's files, `.env`, or a migration file that already exists on `main`.
3. **No scratch files.** Do not create probe scripts, temporary tests, notes or backups in the repo. Use your CLI's own scratch space. Do not edit a `conftest.py` unless your plan lists it.
4. **Database.** There is one shared demo database (Supabase). Never point anything at production. Never run seeds.
   1. Use only the migration numbers assigned to your stream. Apply with `python3 scripts/migrate_db.py` from `LocalDev/`.
   2. A migration that has been applied is frozen. To change it, add a new file with your next number. (A file you wrote but have not applied yet may still be edited.)
   3. Replace only the DB functions your plan says you own, with `CREATE OR REPLACE FUNCTION`, the exact live signature and return shape. `fn-index.txt` in this folder says which migration holds the live body of each function (the last definition wins).
   4. Every statement in a migration must be safe to run twice (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, `CREATE OR REPLACE`, `DROP … IF EXISTS` before `CREATE TRIGGER`).
   5. Tests create their own chapter (`chapter_id` fixture) and assert only inside it. Never assert on global row counts.
5. **Tests.** Backend: `python3 -m pytest <folders your plan names> -q` from `LocalDev/`. Do not run the full suite unless your plan says so (it takes 11 minutes and shares the database with every other agent). Frontend: `npm test && npm run lint` in `LocalDev/greekos/`. A test you had to change because the behaviour changed on purpose goes in your report with one line of reason.
6. **Code style.** Match the file you are in. Smallest change that fixes the root cause; no new abstractions, no new dependencies, no drive-by refactors. A deliberate shortcut gets a `# ponytail: <ceiling>, <upgrade path>` comment. Money is integer cents. Permission checks go through `api.rbac` only.
7. **Commits.**
   - Claude agents (01, 03, 05, 06, 15): commit after each task with the message your plan gives. One logical change per commit, conventional subject (`fix(scope): …`). **No `Co-Authored-By`, no "Generated with", no session links.** Never `git add -A`; stage the files the task names. Do not push.
   - External CLI agents (Cursor, Codex, Antigravity): **do not commit, do not stage, do not run any git command that changes state.** Where your plan says "Checkpoint", make sure the named tests pass and carry on. The orchestrator commits your work after verifying it.
8. **Secrets.** Never print, log or copy values from `.env`. Never put a code, password or token in a test name, a log line or your report.
9. **When stuck.** Two failed attempts at the same step → stop that task, report `BLOCKED` with the exact error, and continue with the next task if it does not depend on it. Do not weaken a test, delete an assertion, or widen a guard to get to green.

Claude agents additionally load these skills before starting: `ponytail:ponytail` (full), `superpowers:test-driven-development`, `superpowers:verification-before-completion`.

## What to hand back

End your run with exactly this block as your final message (plain text):

```
STREAM: <id and name>
FINDINGS:
  F-0xx: FIXED | NOT_REPRODUCED | BLOCKED | PARTIAL — one line
  …
FILES CHANGED: <path>, <path>, …
DELETED FILES: <path>, … (or none)
MIGRATIONS: <file> applied yes/no, …
DB FUNCTIONS REPLACED: <name>, …
TESTS: <command> → <final count line, verbatim>
EXISTING TESTS CHANGED: <test id> — why; … (or none)
OUTSIDE MY LANE: anything you noticed in files you were not allowed to touch
HUMAN FOLLOW-UP: … (or none)
SUGGESTED COMMITS: (external agents only) one line per checkpoint: <message> — <files>
```

## Contracts between streams

These are the only cross-stream interfaces. If yours has to differ, stop and report.

| Contract | Built by | Used by | Shape |
|---|---|---|---|
| Transaction | 01 | 10, 11, 13, 14 | `with get_db().transaction() as tx:` → `tx` is a client on one connection; commit on exit, rollback on error; exit raises if a DB error was swallowed inside |
| Insert-or-ignore | 01 | everyone via `enqueue` | `sb.table(t).insert(rows, ignore_conflict="col").execute()` → `.data` holds only inserted rows |
| Outbox enqueue | 01 | all producers | `enqueue(...)` returns `dict | None`; a real failure is logged (outside a transaction) or raised (inside one) |
| Record payment | 03 | 05 | `POST /api/treasury/payments/record` `{member_id, amount_cents, method, invoice_id?, reference?}` → verify-v2 result; needs `treasury:payment:verify` |
| Coverage | 03 | 08, 09 | invoice coverage lives only in `payment_allocations`; `verified_payments.invoice_id` is always NULL |
| Role errors | 02 | 06 | assign/revoke → 403 `Only an admin can grant or revoke that role`; 409 `The chapter must keep at least one admin. Make someone else an admin first.` |
| Remaining cents | 08 | 09 | `api/treasury/services/remaining.py::remaining_by_invoice(sb, invoices) -> dict[str, int]` |
| Event timing | 08 | 09, 15 | `api/events/core/timing.py`: `chapter_timezone`, `event_start_utc`, `has_started`; column `chapters.timezone` |
| Check-in link read | 10 | 06, 15 | `GET /api/events/{id}/checkin-link` → `{}` or `{event_id, active, expires_at}` for members; full object for managers |
| Check-in deep link | 10 | 06 | `GET /c/{code}` → 302 `{FRONTEND_URL}/?checkin=CODE` |
| Event delete | 11 | 15 | `DELETE /api/events/{id}` → `{deleted: bool, cancelled: bool}`; column `events.cancelled` |
| Provider stamp | 12 | 14 | columns `message_outbox.provider_attempted_at`, `provider_message_id`; reaper parks stamped rows as `failed` |

## Decisions

| # | Decision | Source |
|---|---|---|
| D1 | Finance "Add transaction": all four kinds save to the server. "Record payment" is one officer action (`tr_record_payment` = submit + verify in one transaction). | user |
| D2 | Officers may keep approving their own payments and crediting their own account below $500. F-027 is accepted as is. | user |
| D3 | A refund reopens the invoice it covered (allocation reversals + status refresh). | user |
| D4 | Deleting an event really deletes it only when nothing is attached; otherwise it is cancelled (`cancelled = true`, `required = false`, open jobs and live codes closed) and its attendance and fines stay. Cancelled events are hidden from every list. | user |
| D5 | One timezone per chapter, `chapters.timezone`, default `America/Los_Angeles`. Event `date`/`time` are local to it. No UI to change it yet. | user |
| D6 | Check-in requires being signed in. The public phone form is removed; `/c/CODE` redirects into the app. Members cannot read the door code from the API. | user |
| D7 | A payment is applied to the invoice it was submitted against first; any surplus goes oldest-first. | user |
| D8 | Admin tier. The person who creates a chapter becomes its `admin`. `admin` and `president` can be granted or revoked only by an admin. Several admins may exist; an admin can hand the role to anyone and step down, but the last admin cannot be removed. Existing chapters: the earliest officer becomes admin (one backfill). Every other role stays grantable by any `roles:assign` holder. | user |
| D9 | Permissions come from `member_roles` plus an implicit `member` baseline. `members.role` is display-only, kept in step by the RPCs. One backfill gives every legacy officer a row. | orchestrator |
| D10 | The ledger stays a shadow log (report §10). Amount and owner columns on money rows are frozen by trigger instead. | orchestrator |
| D11 | Payload-hash check for idempotency keys only on the dues run (the one key the UI can reuse); the client regenerates its key when the form changes. Keys still never expire. | orchestrator |
| D12 | `invited` members can be assigned to jobs, security and chair roles; `inactive` and `alumni` cannot. | orchestrator |
| D13 | Usage tracker: name must match a strict pattern, metadata ≤ 1 KB, 600 events per member per hour, rows may be deleted (not updated). | orchestrator |
| D14 | Dashboards, exports and SMS audiences compute balances live with a bulk method; the cache table is no longer trusted by readers. | orchestrator |
| D15 | Inline SMS dispatch stays (blasts go out immediately) but must claim its rows atomically before sending. | orchestrator |
| D16 | SMS consent follows the phone number across chapters (one sender number serves all chapters; STOP must stop everything). F-068 gets documentation only. | orchestrator |
| D17 | R-05 (outbox fairness): no change. Drain capacity is ~600 messages/hour; anonymous signup is capped far below that. | orchestrator |
| D18 | F-065: the signup conflict message stops naming the field. The in-process limiter stays (report §10). Full anti-enumeration would need codes delivered by email only; deferred. | orchestrator |
| D19 | The production guard is armed unless `APP_ENV` is `local` or `test` (or `VERCEL_ENV=development`). Production also rejects localhost `BASE_URL`/`FRONTEND_URL`. | orchestrator |
| D20 | One live fine per event and member (partial unique index). Marking present or excused voids an open fine. The legacy `process-event` fine engine is removed. | orchestrator |
| D21 | One-time codes are wiped from every finished outbox row and such rows cannot be retried (the officer issues a new code). `/api/health` is 503 only when the database is down; a stale cron is `degraded`. | orchestrator |
| D22 | `Prod/` is produced from `LocalDev/` by `scripts/build_prod.sh`, with a CI drift check. Running the sync, migrating production and deploying each need the user's explicit go-ahead. Until the sync runs, `Prod/` is a stale hand copy. | orchestrator |
| D23 | F-026 does not reproduce: SELECT returns ids as strings (checked live 2026-10-05). Stream 01 pins that with tests and changes no code unless they fail. | orchestrator |
| D24 | External CLI agents do not commit. The orchestrator commits after verifying, one commit per logical change. | orchestrator |
| D25 | F-009: the suite's first non-owner test asserts that Supabase's API roles have no table access. RLS policies stay unexercised defense in depth. | orchestrator |

## Worktree setup (done by the orchestrator before each dispatch)

```bash
WT=/home/mshik/GuildOS-wt/audit-<id>
git -C /home/mshik/GuildOS worktree add -b <branch> "$WT" main
cp /home/mshik/GuildOS/LocalDev/.env "$WT/LocalDev/.env"
# frontend streams only:
(cd "$WT/LocalDev/greekos" && npm ci)
```

`run-stream.sh <id>` in this folder does this and launches the external CLI for streams 02, 04, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17. Claude streams (01, 03, 05, 06, 15) are dispatched with the Agent tool (`isolation: worktree`, `model: opus` or `fable`), with this README and the plan as the prompt.

## Browser check (frontend streams)

```bash
cd LocalDev && npm run dev                       # backend :8001 (demo DB) + greekos :3000
```

`DEV_AUTH_BYPASS=1` and `APP_ENV=local` must be in `LocalDev/.env`. Dev login is Jake Martinez (`jake@tke.org`), an officer; use the sidebar "Demo: view as" for a member view. Check desktop and a 390-px-wide viewport. Record what you clicked and what you saw in the report; a screenshot path is welcome.

## Orchestrator runbook

Per stream, after its agent returns:

1. **Lane check.** `git -C $WT status --short` against the plan's allowed files. Anything else: read it, then revert or adopt deliberately. Scratch files are deleted.
2. **Cross-vendor review** (read-only, one call): Grok's work → Luna; Luna's → Grok; Gemini's → Luna; Claude's → Grok. Prompt: the plan, the diff, and "assume this is wrong: find the input that breaks it, the guard that is missing, or the test that proves nothing". Use `../2026-09-30-forensic-audit/run-task.sh` with the findings schema.
3. **Verify.** Read the whole diff. Run the plan's test folders. For streams with migrations, re-read each replaced function against its live predecessor (signature, return shape, nothing dropped).
4. **Fix** what review or verification found, in the worktree. A fix to an applied migration is a new file with the stream's next number.
5. **Commit** (external streams) following the agent's suggested commits, split per logical change, no attribution trailers.
6. **Archive** files the stream deleted: copy them from `main` to `archive/audit-remediation-2026-10/<stream>/` before merging.

Per wave, after all its streams pass:

7. Merge each branch with `git merge --no-ff`, in stream-number order; resolve the shared-file hunks (`api/index.py`, `api/announcements/services/sms.py`, `api/events/api/events.py`) by keeping both sides.
8. `python3 scripts/migration_checksums.py --update` (after stream 07 is merged), commit `chore(migrations): record checksums`.
9. `python3 scripts/migrate_db.py`, then the full suite: `python3 -m pytest -q` in `LocalDev/` and `npm test && npm run lint && npm run build` in `greekos/`. Green before the next wave starts.
10. Delete merged branches, their worktrees and remote branches.

At the end: stream 18 Task 4 (with the user's go-ahead), then the human checklist from stream 18 Task 5.

## Coverage

Every finding and residual, and where it goes.

| ID | Stream | | ID | Stream | | ID | Stream | | ID | Stream |
|---|---|---|---|---|---|---|---|---|---|---|
| F-001 | 06 | | F-020 | 13 | | F-039 | 01 | | F-058 | 03 |
| F-002 | 08 | | F-021 | 01 | | F-040 | 07 | | F-059 | 09 |
| F-003 | 10 | | F-022 | 02 | | F-041 | 17 | | F-060 | 09 (+08 column) |
| F-004 | 09 | | F-023 | 02 (+06 UI) | | F-042 | 04 | | F-061 | 05 |
| F-005 | 13 | | F-024 | 08 (+09 summary, +15 UI) | | F-043 | 11 | | F-062 | 06 |
| F-006 | 02 | | F-025 | 11 | | F-044 | 15 | | F-063 | 12 |
| F-007 | 13 | | F-026 | 01 (not reproduced) | | F-045 | 06 | | F-064 | 16 |
| F-008 | 04 (+18 human) | | F-027 | accepted (D2) | | F-046 | 14 | | F-065 | 13 |
| F-009 | 04 | | F-028 | 08 | | F-047 | 04 | | F-066 | 06 |
| F-010 | 18 | | F-029 | 03 | | F-048 | 04 | | F-067 | 14 |
| F-011 | 01, 10, 11, 13 | | F-030 | 03 (+05 copy) | | F-050 | 14 | | F-068 | documented (D16), 17 |
| F-012 | 11 (+15 UI) | | F-031 | 03 (+17 docs) | | F-051 | 14 | | F-069 | 18 |
| F-013 | 12 | | F-032 | 03 (+05 copy) | | F-052 | 02 | | F-070 | 03, 05 |
| F-014 | 05 (+03 server) | | F-033 | 02 | | F-053 | 11 | | F-071 | 16 |
| F-015 | 08 | | F-034 | 12 | | F-054 | 04 | | R-01 | 07 |
| F-016 | 07 (+18 human) | | F-036 | 10 (+06 UI) | | F-056 | 08 | | R-02 | 14 |
| F-017 | 12 | | F-037 | 14 | | F-057 | 09 | | R-03, R-04 | 01 |
| F-018 | 12 | | F-038 | 17 (+18 human) | | | | | R-05 | no change (D17), 17 |
| F-019 | 12 | | | | | | | | R-06 | 16 |
| | | | | | | | | | R-07 | 13 |
| | | | | | | | | | R-08 | 18 |
