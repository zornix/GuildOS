# Handoff — audit remediation: wave 3 DONE, wave 4 next (updated 2026-10-06, session 3)

Read `00-README.md` first (rules, contracts, decisions, runbook). This file says where things
stand and what a new session does first. The model rules below override the README's model column.

## Where things stand

- **Waves 1–3 (streams 01–15) and stream 18's code tasks are merged to `main` and green.**
  Full backend suite on the wave 3 merge: 1298 passed. Frontend: 143 tests, lint, build ok.
  Ruff clean. Stream 18 (merged after the suite started) adds 9 tests that pass on their own.
- Migrations applied to the demo DB and checksummed through 0201. Numbers used outside the
  README ranges: 0199 (09's fine guard; 0195 left unused because 0196–0198 were applied first)
  and 0201 (09 review fix, in 14's spare range). 0177, 0184–0185, 0189–0190, 0192–0195, 0202
  stay unused.
- All branches and worktrees through wave 3 are deleted. **Nothing is pushed.**
- Stream reports, reviews, deleted files and the demo refund script (gitignored, local):
  `archive/audit-remediation-2026-10/<id>/`. Suite logs: `wave2-full-suite.txt`,
  `wave3-full-suite.txt` there. R-08 residue moved to `archive/residue-2026-10/`.
- `migrate_db.py` warns that the demo DB has `0157_dues_run_bulk_due_at.sql` applied: an old
  rename (that file is now 0158). Harmless.

## Decisions made this session (user)

- **Paid duplicate fines (2026-10-05):** keep the strict "one live fine per event and member"
  index. The demo DB's 8 event/member pairs with several paid fines were refunded through the
  normal refund path (43 refunds, 222,500 cents, chapter Delta Mu) before 0199 applied.
  **Production will need the same hand refunds before 0199 can run** (the migration stops with a
  clear error if two paid fines exist for one pair). Script:
  `archive/audit-remediation-2026-10/09/refund_paid_duplicate_fines.py` (demo-guarded).
- `tr_issue_event_fines` skips a member who has any fine for the event, voided or waived
  included (0201), as the issue route did before.

## Start wave 4 (needs the user's go-ahead)

Wave 4 = **16 (sweep)** and **17 (docs)**. Both are Antigravity · Gemini 3.8 Flash in the README;
`run-stream.sh` maps them to `agy`. Review each with Sol (`review-stream.sh <id> <plan> codex
gpt-6.1-sol medium`).

Carry-overs (put into the dispatch prompts via `EXTRA_FILE`):
- 16: the cron drain routes already have unique operation ids (R-02, stream 14); the legacy
  `fine_processor` and `/api/fines/process-event` are already gone (09); the operations template
  API is gone (11).
- 17: document in `ops-runbook.md`: hand refunds of paid duplicate fines before 0199 on prod; the
  stream 18 checklist is already there under "Before the next production deploy" (extend, do not
  duplicate). Chapter timezone ADR (0007) facts: `chapters.timezone`, `api/events/core/timing.py`,
  `ev_local_start` (0197). Authority ADR (0006): `member_roles` + implicit `member` baseline (D9),
  admin tier (D8).

Then stream 18:
- **Task 2 apply** (demo only, needs go-ahead): `python3 scripts/purge_test_chapters.py --apply`.
  Dry run: 26,751 test chapters older than 2 days (37,519 members, 29,786 audit rows, …); only
  "Delta Mu" plus four odd one-off names are kept.
- **Task 4** (after wave 4, needs go-ahead): `bash LocalDev/scripts/build_prod.sh --check`
  shows the drift (at last check: 91 differing, 151 missing, 10 extra), then sync, Prod smoke,
  commit, then add the CI drift step.

## Human follow-ups collected so far

The full checklist is in `LocalDev/docs/ops-runbook.md` → "Before the next production deploy".
Added this session:
- Refund paid duplicate fines on prod before running 0199 (see above).
- Set `BASE_URL`, `FRONTEND_URL` in Vercel to public origins; `APP_ENV` must not be
  `local`/`test` there, or production refuses to boot.
- Delete the nine unused names from `LocalDev/.env` (list in the runbook).
- Demo DB rows left by browser checks: wave 1 (fine Alex Rivera $7.50, invoice Chris Park
  $11.25, adjustment Ethan Davis −$1.50, one attendance row); wave 3 stream 15 left a cancelled,
  hidden event "S15 check 5" (dated 2099) with one attendance row for Jake. Harmless.

## Model rules (user directive 2026-10-05)

- **Every Claude subagent runs on Opus** (`model: "opus"`), never Fable.
- Prefer the external CLIs: **Sol = `codex -m gpt-6.1-sol`** and **Gemini 3.8 Flash**
  (`agy --model "Gemini 3.8 Flash (Medium)"`). Cursor/Grok is out of usage.
- Each stream is reviewed by the other vendor. Sol fix-up runs worked well for review gaps
  (09, 15): a custom prompt with the remaining tasks, same worktree, `codex exec … -o
  report-fixup.txt`.
- Keep the orchestrator light: read `report.txt` and `review/result.json`, diff DB functions
  programmatically (`fndiff`), stage hunks with a `git apply --cached` helper (re-list hunks after
  each partial stage; numbers shift).

## Lessons from waves 2–3

- Every new DB function needs `REVOKE ALL … FROM PUBLIC` in the same migration; say so in each
  dispatch. `CREATE OR REPLACE` keeps existing grants.
- Codex's sandbox can only write inside the worktree; point any out-of-repo output at the
  worktree's gitignored `archive/`.
- Agent worktrees: create them yourself (`git worktree add`, copy `.env`, `npm ci`) and tell the
  agent the path; do not rely on `isolation: worktree`.
- Cross-stream test leftovers show up only in the full suite after merging (wave 2: a removed
  route still listed in `test_route_registration.py`).

## Cost notes

Session 3: waves 2 and 3. One Opus agent (stream 15, ~206k tokens); everything else on Sol and
Gemini. Orchestrator context ~210k at the end of wave 3.
