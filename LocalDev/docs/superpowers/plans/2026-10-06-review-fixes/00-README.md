# Review fixes — directing guide

> **For agentic workers:** you were given this file plus ONE numbered plan. Read "Rules for every agent" and "What to hand back" here, then execute your plan task by task. Everything else in this file is background you may consult. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `LocalDev/docs/audit/remediation-review.md` — the post-remediation Opus review of all 18 audit streams (0 P0, 3 P1, 27 P2, 41 P3). Each plan names the review sections it fixes; read those sections before you start. Issue ids below are `RV-<stream>-<n>` where `<stream>` is the review's stream heading and `<n>` counts its bullets top to bottom (so RV-06-1 is the roster P1).
**Written:** 2026-10-06 by the orchestrating session (Claude Fable 5). Product decisions were made by the user on 2026-10-06 and are recorded under "Decisions". They are not open for re-litigation; if one turns out to be impossible, stop and report.
**Dedup:** the review's 71 bullets collapse to 68 unique issues. Three were reported twice and are fixed once: the event-type race (01+11, plan 04), self check-in not voiding fines (09+10, plan 07), the balances CSV mixing live and cached numbers (08+09, plan 08).

## Streams

All implementation agents are **Codex · gpt-6.1-sol · medium** dispatched headless by the orchestrator (`run-stream.sh`). Every stream is reviewed by a **Claude Opus** read-only reviewer before merge. The orchestrator commits and merges.

| # | Plan | Wave | Branch | Fixes (review sections) | Migrations |
|---|---|---|---|---|---|
| 01 | `01-frontend-shell.md` | 1 | `fix/review-01-frontend` | 06 all, 05 all, 15, 14 (Retry button) | none |
| 02 | `02-authority.md` | 1 | `fix/review-02-authority` | 02 all | 0206 |
| 03 | `03-treasury.md` | 1 | `fix/review-03-treasury` | 03 all | 0207–0209 |
| 04 | `04-events-platform.md` | 1 | `fix/review-04-events-platform` | 01 all, 11 P2 + race + cancelled-event (events.py part) | 0210 |
| 05 | `05-db-guards.md` | 1 | `fix/review-05-db-guards` | 04 all (F-042, F-054, supervisors, lock mode) | 0211–0212 |
| 06 | `06-ops-ci.md` | 1 | `fix/review-06-ops-ci` | 18 all, 07 all but the CLAUDE.md note | none |
| 07 | `07-fines-attendance.md` | 2 | `fix/review-07-fines-attendance` | 09 all, 10 all, 11 cancelled-event (attendance part) | 0213–0214 |
| 08 | `08-balance-readers.md` | 2 | `fix/review-08-balance-readers` | 08 all (+ 09 CSV dup) | none |
| 09 | `09-outbox.md` | 2 | `fix/review-09-outbox` | 12 all | 0215 |
| 10 | `10-error-mapping.md` | 2 | `fix/review-10-errors` | 16 all, 13, 14 (health, docstring), 11 (`_rpc_http_error`) | none |
| 11 | `11-docs.md` | 3 | `fix/review-11-docs` | 17 all, 07 CLAUDE.md note | none |

**Waves.** A wave starts only after the previous wave is merged to `main` and the full suite is green. Inside a wave every stream runs in parallel in its own worktree; file lanes are disjoint by construction — stay in yours. Wave 2 streams touch files wave 1 changed (events.py, fines, index.py), which is why they wait. Docs go last so they describe the final code.

## Decisions (user, 2026-10-06 — binding)

| Id | Decision |
|---|---|
| D-R1 | **Restore the localhost `FRONTEND_URL` refusal** for preview and unknown (`VERCEL_ENV`/`APP_ENV` unset) environments. Local dev (`APP_ENV` local/test) still allows it. (Review 13.) |
| D-R2 | **Prod `DATABASE_URL` points at the demo project for now — on purpose.** The `LocalDev/CLAUDE.md` "Temporary" note is correct and stays. Review 17's question is closed with no code or doc change. |
| D-R3 | **Event supervisors get the D12 inactive-member guard** (active members only), same as chairs and security. Broader alumni/inactive product behaviour is TBD — do not build beyond the status check. (Review 04.) |
| D-R4 | *(orchestrator, from the frontend hard rules)* The roster has no add-member or set-standing endpoint **by design** (invite/import creates members; standing is derived server-side). Fix RV-06-1 by **removing the two fake controls**, not by inventing endpoints. |

## Rules for every agent

1. **Reproduce first.** Every fix starts with a test that fails on your untouched branch for the reason the review describes. If you cannot make it fail, do not change production code for that issue: mark it `NOT_REPRODUCED` in your report, say what you tried, keep any useful regression test, and move on. One audit finding (F-026) already turned out to be false this way. Doc-only issues (plan 11) are exempt; verify the claim against the code instead.
2. **Stay in your lane.** Change only the files your plan lists under "Allowed files". If a fix seems to need another file, stop that task and report it as `BLOCKED` with the file and the reason. Never edit `Prod/`, `archive/`, another stream's files, `.env`, or a migration file that already exists on `main`.
3. **No scratch files.** Do not create probe scripts, temporary tests, notes or backups in the repo. Use your CLI's own scratch space. Do not edit a `conftest.py` unless your plan lists it.
4. **Database.** There is one shared demo database (Supabase). Never point anything at production. Never run seeds.
   1. Use only the migration numbers assigned to your stream. Apply with `python3 scripts/migrate_db.py` from `LocalDev/`, then run `python3 scripts/migration_checksums.py --update`.
   2. A migration that has been applied is frozen. To change it, add a new file with your next number. (A file you wrote but have not applied yet may still be edited.)
   3. Replace only the DB functions your plan says you own, with `CREATE OR REPLACE FUNCTION`, the exact live signature and return shape. `fn-index.txt` in this folder says which migration holds the live body of each function (the last definition wins). Base your new body on that live body, not on an older copy.
   4. Every statement in a migration must be safe to run twice (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, `CREATE OR REPLACE`, `DROP … IF EXISTS` before `CREATE TRIGGER`). Every NEW function gets `REVOKE ALL ON FUNCTION … FROM PUBLIC;` in the same migration (`CREATE OR REPLACE` of an existing one keeps its grants).
   5. Tests create their own chapter (`chapter_id` fixture) and assert only inside it. Never assert on global row counts.
5. **Tests.** Backend: `python3 -m pytest <folders your plan names> -q` from `LocalDev/`. Do not run the full suite unless your plan says so (it takes 11 minutes and shares the database with every other agent). Frontend: `npm test && npm run lint` in `LocalDev/greekos/`. A test you had to change because the behaviour changed on purpose goes in your report with one line of reason.
6. **Code style.** Match the file you are in. Smallest change that fixes the root cause; no new abstractions, no new dependencies, no drive-by refactors. A deliberate shortcut gets a `# ponytail: <ceiling>, <upgrade path>` comment. Money is integer cents. Permission checks go through `api.rbac` only.
7. **Git: do not commit, do not stage, do not run any state-changing git command.** Where your plan says "Checkpoint", make sure the named tests pass and carry on. The orchestrator commits your work after verifying it.
8. **Secrets.** Never print, log or copy values from `.env`. Never put a code, password or token in a test name, a log line or your report.
9. **When stuck.** Two failed attempts at the same step → stop that task, report `BLOCKED` with the exact error, and continue with the next task if it does not depend on it. Do not weaken a test, delete an assertion, or widen a guard to get to green.

## What to hand back

End your run with exactly this block as your final message (plain text):

```
STREAM: <id and name>
ISSUES:
  RV-xx-n: FIXED | NOT_REPRODUCED | BLOCKED | PARTIAL — one line
  …
FILES CHANGED: <path>, <path>, …
DELETED FILES: <path>, … (or none)
MIGRATIONS: <file> applied yes/no, …
DB FUNCTIONS REPLACED: <name>, …
TESTS: <command> → <final count line, verbatim>
EXISTING TESTS CHANGED: <test id> — why; … (or none)
OUTSIDE MY LANE: anything you noticed in files you were not allowed to touch
HUMAN FOLLOW-UP: … (or none)
SUGGESTED COMMITS: one line per checkpoint: <message> — <files>
```

## Contracts between streams

- **Migration numbers are assigned above and never traded.** If you need one more than assigned, report `BLOCKED`.
- Plan 04 owns `api/events/services/events.py` and `api/platform/postgres.py` in wave 1; plan 07 may touch `events.py` in wave 2 (it branches after 04 is merged).
- Plan 10 owns `api/index.py`; nobody else edits it.
- Plan 01 owns everything under `greekos/`; no backend stream touches the frontend.
- Plan 11 owns every `*.md`; code streams change no docs (docstrings in code files are fine).
- The event lock key convention is `pg_advisory_xact_lock(hashtext('ev_attendance:' || event_id))` where plans say "event lock"; the security lock is `hashtext('ev_security:' || event_id)` (see 0175 for the existing taker).

## Runbook (orchestrator)

For each stream: `run-stream.sh <id>` (creates worktree from current `main`, copies `.env`, dispatches Sol) → read `report.txt` → dispatch an Opus reviewer (read-only, adversarial, against `git -C <worktree> diff` + the plan) → fix gaps (Sol fix-up run in the same worktree, or by hand) → commit per suggested checkpoints (no attribution trailers) → `git merge --no-ff` → delete branch + worktree → stream tests green. After each wave: full suite + `greekos` tests + lint from the merged `main`.
