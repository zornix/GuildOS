# Handoff — audit remediation: wave 1 DONE, start wave 2 (updated 2026-10-05, session 2)

Read `00-README.md` first (rules, contracts, decisions, runbook). This file says where things
stand and what a new session does first. The model rules below override the README's model column.

## Where things stand

- **Wave 1 (streams 01–07) is merged to `main` and green.** Full backend suite: 1146 passed
  (1144 + 2 permission tests fixed in `c94b703`). Frontend: 134 tests, lint, build ok.
  Migrations 0162–0175 and 0203–0205 are applied to the demo DB; checksums recorded.
- All wave 1 branches and worktrees are deleted. **Nothing is pushed.**
- Stream reports and reviews (gitignored, local): `archive/audit-remediation-2026-10/<id>/`.
  `WAVE1-STATUS.md` there summarises session 1.
- Next free migration numbers: wave 2 uses the README ranges 0176–0194; 0203–0205 are taken.

## Start wave 2 (new session)

Wave 2 = streams **08, 10, 11, 12, 13** (README table). All run in parallel, each in its own
worktree via `run-stream.sh <id>` (run_in_background). Then, per stream: read `report.txt`,
review with the other CLI via `review-stream.sh`, read only `review/result.json`, fix, merge
`--no-ff` one at a time, run the full suite, delete branch + worktree. Check in with the user
before wave 3.

1. Put the carry-overs below into each affected stream's prompt: write that stream's lines
   to a file and run `EXTRA_FILE=<file> run-stream.sh <id>` (08, 11, 13 have carry-overs).
   `SETUP_ONLY=1` prints the final prompt without launching.
2. `run-stream.sh` already maps: 08/10/11/13 → Codex `gpt-6.1-sol`, 12 → Codex (Grok out).
3. Watch each with a short health check after ~2 min (stderr growing = working).

## Model rules (user directive 2026-10-05)

- **Every Claude subagent runs on Opus** (`model: "opus"`), never Fable, even where a plan
  names Fable. Two Fable frontend agents cost >300k tokens each and ran session 1 out.
- Prefer the external CLIs for anything that is not the orchestrator's own judgement:
  **Sol = `codex -m gpt-6.1-sol`** and **Gemini 3.8 Flash** (`agy --model "Gemini 3.8 Flash (Medium)"`).
  Cursor/Grok ran out of usage in session 2; Luna is not on the user's list. Fall back to
  Opus only if both CLIs fail.
- README rows that say Luna or Grok → Sol. Gemini rows unchanged.
- Keep the orchestrator light: never `cat` whole diffs; read `result.json`, diff DB functions
  programmatically (see "Tools").

## Carry-overs for wave 2 (put these into the dispatch prompts)

- Outbox contract (01): `enqueue`/`enqueue_many` raise inside a transaction client, but
  `api/events/notifications.py` (`_enqueue`, `notify_event_created`) and
  `api/auth/notifications.py` (`notify_code`) still catch and swallow. Streams 11 and 13 must
  make those wrappers re-raise when `client._pool.in_tx` is set before adopting `transaction()`.
- `api/treasury/services/member_dashboard.py::_direct_paid_cents` and the payment entry in
  `services/reports.py` read `verified_payments.invoice_id`, always NULL since 0165: stream 08
  deletes them.
- `GET /api/fines/` rows gain `remaining_cents` (05 fix-up); stream 08's `remaining_by_invoice`
  can replace that implementation. Stream 08 also joins `payment_submissions.method` into the
  treasury dashboard's `recent_payments` (`services/reports.py`) so the Payments table shows it.
- Test factories: `member_factory(role="officer")` (tests/treasury and tests/auth conftest) now
  also writes the `member_roles` row. A test that wants a column-only officer sets the column
  with `UPDATE members SET role='officer'`.
- Migration numbers taken outside the README ranges: 0203 (02), 0204 and 0205 (03). Wave 2 keeps 0176–0194 as planned.
- Usage-cap race in `usage.track` accepted as the planned ponytail ceiling (D13).
- Demo DB rows left by browser checks: a fine (Alex Rivera, $7.50), an invoice (Chris Park,
  $11.25), an adjustment (Ethan Davis, −$1.50), one attendance row (Alex Rivera, "Chapter
  Meeting - March"). Harmless; delete if they bother anyone.

## Tools

- `review-stream.sh <id> <plan.md> <codex|cursor|agy> [model] [effort]` (this folder):
  diffs the worktree against main, builds the adversarial prompt, runs the CLI read-only via
  `../2026-09-30-forensic-audit/run-task.sh`, writes `archive/audit-remediation-2026-10/<id>/review/result.json`.
  Cursor gets no inline diff (argv limit); it reads `git diff main` itself. Run with `nohup … &`
  and watch for `review/meta.txt`. Create `archive/audit-remediation-2026-10/<id>/` first.
- `run-stream.sh <id>` sets up the worktree (copies `.env`) and launches the stream's CLI.
  Codex streams run `gpt-6.1-sol`; Cursor/Grok streams now go to Codex too.
- DB function diff against the live predecessor (the pattern used all day):
  parse `CREATE OR REPLACE FUNCTION name(...)$$;` blocks from the new migration and from the
  last earlier migration defining the same name, `difflib.unified_diff` them. Expect only the
  planned hunk.
- `pytest` refuses to run when the demo DB is behind the checkout's migrations; apply with
  `bash ../local-dev-scripts/scripts/with-demo-db.sh python3 scripts/migrate_db.py` (plain
  `python3 scripts/migrate_db.py` now also reads `DATABASE_URL` from `.env`, stream 07).
- Never `pkill -f` a pattern that appears in your own command line.

## Cost notes

Session 1 Claude usage: orchestrator ~400k context (read every diff itself), Opus agents
01 ≈170k and 03 ≈260k, Fable agents 05 ≈365k and 06 ≈310k. Session 2 (03 fix-up by Sol,
merges, full suite) used ~120k orchestrator context and no Claude subagents.
External CLIs are not Claude usage. To spend less Claude: dispatch implementation to
Sol/Gemini via `run-stream.sh`, review with the other CLI, and keep Opus for the two
things that need it (orchestrator judgement calls, and streams where a CLI fails twice).
