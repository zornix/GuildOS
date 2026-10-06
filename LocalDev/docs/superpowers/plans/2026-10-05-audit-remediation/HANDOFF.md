# Handoff — audit remediation: wave 2 DONE, wave 3 next (updated 2026-10-05, session 3)

Read `00-README.md` first (rules, contracts, decisions, runbook). This file says where things
stand and what a new session does first. The model rules below override the README's model column.

## Where things stand

- **Waves 1 and 2 (streams 01–08, 10–13) are merged to `main` and green.** Full backend suite
  after the wave 2 merges: 1245 passed, 1 failed (`test_legacy_paths_still_registered`, a
  cross-stream leftover fixed in `241734b`; that file passes). Ruff clean. Wave 2 did not
  touch `greekos/`.
- Migrations applied to the demo DB and checksummed: 0176, 0178–0183, 0186–0188, 0191.
  Free in the wave 2 ranges: 0177, 0184–0185, 0189–0190, 0192–0194 (do not reuse; wave 3 has
  its own ranges 0195–0202).
- All wave 2 branches and worktrees are deleted. **Nothing is pushed.**
- Stream reports, reviews and files the streams deleted (gitignored, local):
  `archive/audit-remediation-2026-10/<id>/` (`report.txt`, `review/result.json`, `deleted/`).
  Full-suite log: `archive/audit-remediation-2026-10/wave2-full-suite.txt`.
- `migrate_db.py` warns that the demo DB has `0157_dues_run_bulk_due_at.sql` applied: an old
  rename (that file is now 0158). Harmless; stream 18 can tidy the recorded name.

## How wave 2 went (so wave 3 can copy it)

- All five ran on Codex `gpt-6.1-sol` via `run-stream.sh` in 8–15 minutes each; reviews by
  Gemini 3.8 Flash via `review-stream.sh <id> <plan> agy "Gemini 3.8 Flash (Medium)"` (4–12 min).
- Orchestrator fixes made on the branches: 0180/0183 revoke PUBLIC on the two new functions
  (`at_checkin_self`, `ev_delete_or_cancel_event`) — **every new DB function needs
  `REVOKE ALL … FROM PUBLIC`; put that in each wave 3 dispatch**; cancelled events refuse edits
  (`_get_event_row` filters `cancelled`); `POST /api/tasks/{id}/status` maps unknown RPC errors
  through `_rpc_http_error` (security task was a 500); stream 08's calendar switched to
  `remaining_by_invoice` and the old coverage helpers deleted; two announcement tests now
  create invoice debt (balances are live, D14).
- Review findings dismissed with reason: `CREATE OR REPLACE` keeps grants (12); member ids are
  per chapter so `member_outstanding(member_id)` is chapter-scoped (08); the DB client has no
  PostgREST 1000-row cap (08); ids come back as strings (D23).
- Accepted ceiling: inline SMS `dispatch_send` sets the send row's status from the rows it
  claimed itself; if the cron claimed some in the same second, the send row can say `sent`
  while those are still in flight (12).
- Committing: `hunks.py`-style partial staging (`git diff HEAD -- f` split on `@@`, apply
  chosen hunks with `git apply --cached`). Hunk numbers shift after each partial stage —
  re-list before every use.

## Start wave 3 (needs the user's go-ahead)

Wave 3 = **09, 14, 15**, then **18** (orchestrator, needs the user for anything touching prod).

1. Carry-overs (put into the dispatch prompts via `EXTRA_FILE`):
   - All: new DB functions get `REVOKE ALL ON FUNCTION … FROM PUBLIC` in the same migration.
   - All: `member_factory(role="officer")` also writes the `member_roles` row; a column-only
     officer is `UPDATE members SET role='officer'`.
   - 09: `GET /api/fines/` computes `remaining_cents` its own way; switch it (and
     `fine_summary`) to `api/treasury/services/remaining.py::remaining_by_invoice`.
     `api/events/core/timing.py` has `chapter_timezone`, `event_start_utc`, `has_started`.
   - 14: templates now live at `api/platform/message_templates.py`; outbox rows have
     `provider_attempted_at` / `provider_message_id`; the reaper parks stamped rows `failed`.
   - 15: `DELETE /api/events/{id}` → `{deleted, cancelled}`; cancelled events 404 on read and
     edit; `GET /api/events/{id}/checkin-link` → `{}` or `{event_id, active, expires_at}` for
     members; `/c/{code}` → 302 `{FRONTEND_URL}/?checkin=CODE`.
2. 09 and 14 → `run-stream.sh` (Codex Sol). 15 is frontend: Agent tool, `model: "opus"`,
   `isolation: worktree`, or Sol if the user prefers no Claude usage.

## Human follow-ups collected so far

- Before the next production deploy: set `BASE_URL` and `FRONTEND_URL` in Vercel to the public
  origins and make sure `APP_ENV` is not `local`/`test` there — production refuses to boot
  otherwise (13). `/c/CODE` redirects to `FRONTEND_URL` (10).
- `LocalDev/.env` still carries nine unused names (ESCALATION_DELAY_MINUTES,
  FEATURE_SECRETARY_COMMS, FEATURE_VP_OPERATIONS, MESSAGE_WEBHOOK_SECRET, SENDGRID_API_KEY,
  SENDGRID_FROM_EMAIL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL); delete by
  hand. `APP_ENV` is already set.
- Demo DB rows left by wave 1 browser checks (fine for Alex Rivera $7.50, invoice for Chris Park
  $11.25, adjustment for Ethan Davis −$1.50, one attendance row). Harmless.

## Model rules (user directive 2026-10-05)

- **Every Claude subagent runs on Opus** (`model: "opus"`), never Fable, even where a plan
  names Fable.
- Prefer the external CLIs: **Sol = `codex -m gpt-6.1-sol`** for implementation and
  **Gemini 3.8 Flash** (`agy --model "Gemini 3.8 Flash (Medium)"`) for review. Cursor/Grok is
  out of usage. Fall back to Opus only if both CLIs fail.
- Keep the orchestrator light: read `report.txt` and `review/result.json`, diff DB functions
  programmatically (`fndiff`: parse `CREATE OR REPLACE FUNCTION … $$;` blocks from the new
  migration and the last earlier one defining the same name, `difflib.unified_diff`).

## Tools

- `run-stream.sh <id>` (this folder): worktree + `.env` + headless CLI; `EXTRA_FILE=` appends
  carry-overs; `SETUP_ONLY=1` prints the prompt.
- `review-stream.sh <id> <plan.md> <codex|cursor|agy> [model] [effort]`: read-only review,
  writes `archive/audit-remediation-2026-10/<id>/review/result.json`.
- `pytest` refuses to run when the demo DB is behind the checkout; apply with
  `python3 scripts/migrate_db.py` from `LocalDev/`.
- Never `pkill -f` a pattern that appears in your own command line.

## Cost notes

Session 3 (wave 2): no Claude subagents; orchestrator context stayed small by reading reports,
review JSON and targeted hunks only.
