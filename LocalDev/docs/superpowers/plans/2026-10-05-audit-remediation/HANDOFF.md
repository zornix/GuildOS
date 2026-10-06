# Handoff — audit remediation: ALL DONE including the final review fixes (2026-10-06)

Read `00-README.md` first (rules, contracts, decisions, runbook). The model rules below override
the README's model column.

## Start here (next session)

1. ~~Review findings~~ **DONE 2026-10-06**: all 68 unique review issues fixed and merged — see `../2026-10-06-review-fixes/RESULTS.md`. Remaining below: golden dataset and the Prod sync.
   found 0 P0, 3 P1, 27 P2, 41 P3. Six audit findings are only partly fixed (F-045, F-064,
   R-06, F-042, F-054, F-041). Nothing in it is fixed yet. Ask the user the three questions
   at its top before fixing (preview `FRONTEND_URL` rule; is prod `DATABASE_URL` still demo;
   does D12 cover supervisors).
2. Golden dataset: brainstorm paused (section below); resume after the user says so.
3. Stream 18 Task 4 (sync `Prod/`) still needs the user's go-ahead, AND must first fix review
   P1 18 (`build_prod.sh` would delete `Prod/fratos/vercel.json`).

## Where things stand (2026-10-06)

- **All 18 streams are merged to `main`.** Full suite on the final merge: 1329 passed.
  Frontend 143 tests, lint, build ok. Ruff clean. Nothing pushed. All stream branches and
  worktrees deleted.
- Demo DB purged of 26,751 old test chapters (stream 18 Task 2, user go-ahead); only Delta Mu
  and four oddly named one-offs remain besides fresh test chapters.
- E2E browser testing is GitHub issue #107.
- **Sol (Codex) hit its usage limit on 2026-10-06**; Opus reviewers/fixers were used instead
  for stream 16 and the final review. Gemini (agy) still worked.

## Older notes (session 3, before wave 4)

## Decisions made this session (user)

- **Paid duplicate fines (2026-10-05):** keep the strict "one live fine per event and member"
  index. The demo DB's 8 event/member pairs with several paid fines were refunded through the
  normal refund path (43 refunds, 222,500 cents, chapter Delta Mu) before 0199 applied.
  **Production will need the same hand refunds before 0199 can run** (the migration stops with a
  clear error if two paid fines exist for one pair). Script:
  `archive/audit-remediation-2026-10/09/refund_paid_duplicate_fines.py` (demo-guarded).
- `tr_issue_event_fines` skips a member who has any fine for the event, voided or waived
  included (0201), as the issue route did before.

## Golden dataset (brainstorm paused until wave 4 is merged — user, 2026-10-06)

Resume with `superpowers:brainstorming` (architectural path) at "present design sections".
Decisions so far (user):
- Both: every audit issue linked to the test that proves it fixed, AND a known-answer chapter.
- The chapter is built fresh each run from a data file, with enough data that **every user
  workflow** can be tested automatically.
- Workflows are tested **through the API** for now. Browser E2E later: issue #107.
- Expected answers are **written by hand from the rules (D1–D25), money and standing first**;
  not recorded from today's app.
- Gate: one command (`npm run golden`, a few minutes) that every agent and every merge to
  `main` must pass; also its own CI step.
- Proposed, awaiting approval: approach A — `@pytest.mark.golden("F-0xx")` markers on
  regression tests plus an exemptions file (decision/human/docs/not reproduced) and a self-check
  that every finding in `docs/audit/2026-09-30-findings.json` is covered; `tests/golden/
  chapter.yaml` + API builder + hand-written `expected.yaml`; one workflow test file per area,
  each building its own chapter; ~35–40 workflows over 138 API operations.

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
