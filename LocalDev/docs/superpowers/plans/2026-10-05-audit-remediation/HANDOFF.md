# Handoff — audit remediation, end of orchestrator session 1 (2026-10-05)

Read `00-README.md` first (rules, contracts, decisions, runbook). This file says where
wave 1 actually stands and what the next session does first. Model rules below override
the README's per-stream model column.

## Model rules (user directive 2026-10-05)

- **Every Claude subagent runs on Opus** (`model: "opus"`), never Fable, even where a plan
  names Fable. Two Fable frontend agents cost >300k tokens each and ran the session out.
- Prefer the external CLIs for everything that is not the orchestrator's own judgement:
  **Gemini 3.8 Flash** (`agy`, `--model "Gemini 3.8 Flash (Medium)"`) and **GPT-6 Sol**
  (`codex -m gpt-6-sol`). Luna (`gpt-6-luna`) and Grok (`cursor agent --model grok-4.7-medium`)
  worked today but the user listed only Gemini and Sol as still available; try them first and
  fall back to Opus if a provider is out.
- Keep the orchestrator session light: do not `cat` whole diffs into context. Use the review
  script below and read only `result.json`; diff DB functions programmatically (see "Tools").
- Streams 08–17 in the README table that say Luna → use Sol. Streams that say Grok → try
  Grok; if it fails, Sol. Gemini streams unchanged.

## Wave 1 state

Nothing is pushed. `main` is at `ea7c95d` (+ this handoff) with five streams merged:

| Stream | Merged to main | Branch/worktree | Open items |
|---|---|---|---|
| 01 db-client | yes (9 commits) | still exists, delete | none |
| 02 authority | yes (4 commits) | still exists, delete | none |
| 04 db-guards | yes (5 commits) | still exists, delete | none |
| 06 frontend-shell | yes (9 commits) | still exists, delete | none |
| 07 ci-tooling | yes (4 commits) | still exists, delete | none |
| 03 treasury-rpcs | **no** | `fix/audit-03-treasury-rpcs`, `/home/mshik/GuildOS-wt/audit-03`, 8 commits, clean | two P0 review findings to fix (below) |
| 05 finance-tab | **no** | `fix/audit-05-finance-tab`, `/home/mshik/GuildOS-wt/audit-05`, 5 commits + an Opus fix-up agent was mid-flight | check its result (below) |

Worktree cleanup for 01/02/04/06/07 was interrupted (a `pkill -f uvicorn` matched the
shell). Finish it: `git worktree remove --force /home/mshik/GuildOS-wt/audit-0{1,2,4,6,7}`
then `git branch -d` the five branches (`-d` refuses anything unmerged).

Reviews done and read: 01 (Grok), 02 (Luna), 03 (Sol), 04 (Luna), 05 (Grok), 06 (Grok),
07 (Luna). JSON under `archive/audit-remediation-2026-10/<id>/review/result.json`
(gitignored, local only). Per-stream agent reports: external streams in
`archive/audit-remediation-2026-10/<id>/report.txt`; Claude streams only in the old
session transcript, summarised in `archive/audit-remediation-2026-10/WAVE1-STATUS.md`.

### Stream 03 — fix before merge (Sol review, both P0, both confirmed by reading the SQL)

Worktree `/home/mshik/GuildOS-wt/audit-03`. Migration numbers: 0165–0170 are applied and
frozen; 0204 (freeze-trigger revoke) is applied too. **Next free number for 03 fixes: 0205.**

1. **Reallocation ignores refunds.** `tr_reallocate_payment` (body in `0165`) caps by the
   payment's full `amount_cents`; after a refund it can re-cover what was refunded. Fix in
   0205: cap allocatable cents by `amount_cents − SUM(active refunds)`; test: pay 10000,
   refund 4000, reallocate 10000 → raises / allocates at most 6000.
2. **`tr_record_payment` idempotency crosses members.** It derives inner keys
   `p_idempotency_key || ':submit'` / `':verify'`, so a key that collides with an existing
   `tr_submit_balance_payment` key replays another member's submission and verifies it.
   Fix in 0205: give record-payment its own `idempotency_keys` operation
   (`'record_payment'`) that stores a request hash of (member, amount, method, invoice,
   reference) and refuses a replay whose hash differs; derive the inner keys from
   `'record:' || key` so they cannot collide with client-issued submit keys. Test: member A
   submits with key `K:submit`; officer records for B with key `K` → B's payment, not A's.
3. P2s (do if cheap): `test_record_payment_is_atomic` fails before any insert (make the
   failure happen after a valid submission); add a refund-larger-than-still-allocated test.

Then: `python3 -m pytest tests/treasury tests/auth/test_rpc_privileges.py -q` in the
worktree, commit (`fix(treasury): …`, no trailers), merge with `--no-ff`.

Dispatch choice: this is SQL on money → **Grok if available, else Sol**, read-only review
afterwards by the other one. If both are out, Opus.

### Stream 05 — pick up the fix-up agent's result

An Opus agent was dispatched (same session) to fix the Grok review findings on
`/home/mshik/GuildOS-wt/audit-05`; when this handoff was written it had modified
`LocalDev/api/treasury/api/fines_legacy.py` and `LocalDev/tests/treasury/test_v1_fines.py`
(adding `remaining_cents` to `GET /api/fines/`) and not yet committed. Its task list, in
priority order (it was told one commit per item, tests first):

1. P0 Mark paid posts the fine's face value even when partly paid; unpaid-fines total sums
   face values → backend `remaining_cents` on the fines list + frontend uses it.
2. P1 Balances "Record payment" shortcut pays the standing figure oldest-first → remove it.
3. P1 `adaptPayments` hardcodes "Dues / Ledger Credit" → show the real method.
4. P2 `backendDown` does not block the four actions → thread it into useFinance, reject up front.
5. P2 member reset keyed on first roster name → key on `currentMember?.id`.
6. P2 dues-run key ignores candidate-list changes → add sorted ids to the key deps.
7. P2 event-fine retry: "already fined" skip is not an error.
8. P2 failed refetch after a landed write toasts plain success → say "saved, lists not reloaded".
9. P2 one node:test for `submitTransaction` with a fake api (key header, pending toast, 403).
10. P3 `handleIssueFine` requires `amountCents`.

Next session: `git -C /home/mshik/GuildOS-wt/audit-05 log --oneline main..HEAD` and
`status --short`. If the agent finished, verify (`npm test && npm run lint && npm run build`
in `LocalDev/greekos`, plus `python3 -m pytest tests/treasury/test_v1_fines.py -q`) and merge.
If it died mid-way, finish the uncommitted item or revert it, then dispatch the remaining
items to **Gemini 3.8 Flash** (frontend, well-specified) with the list above.

Merge note: 05 and 06 both touched `src/App.tsx` and `src/hooks/useAppData.ts`; 06 is on
main, so expect small conflicts in 05's merge. Keep both sides. After merging 05, delete
`useAppData.ts`'s `enqueueOutbox: () => {}` line, the `EnqueueOutbox` type in
`useOutbox.ts`, `finance.setLedger([])` and the unused `ledger`/`LedgerEntry` (06 and 05 each
flagged these as the other's leftovers).

## Finish wave 1 (README runbook steps 8–10)

```bash
cd /home/mshik/GuildOS/LocalDev
python3 scripts/migration_checksums.py --update      # 0162–0175, 0203, 0204 (+0205)
git add migrations/CHECKSUMS && git commit -m "chore(migrations): record checksums"
bash ../local-dev-scripts/scripts/with-demo-db.sh python3 scripts/migrate_db.py
python3 -m pytest -q                                  # ~11 min; baseline on 03's branch was 1057 passed
cd greekos && npm ci && npm test && npm run lint && npm run build
```

Expected noise: the demo DB has `0157_dues_run_bulk_due_at.sql` applied from an old branch
(warning only). Then delete every merged branch and worktree, and **check in with the user**
before wave 2 (that was the user's instruction).

## Wave 2 prerequisites and carry-overs (put these into the wave 2 dispatch prompts)

- Outbox contract (01): `enqueue`/`enqueue_many` raise inside a transaction client, but
  `api/events/notifications.py` (`_enqueue`, `notify_event_created`) and
  `api/auth/notifications.py` (`notify_code`) still catch and swallow. Streams 11 and 13 must
  make those wrappers re-raise when `client._pool.in_tx` is set before adopting `transaction()`.
- `api/treasury/services/member_dashboard.py::_direct_paid_cents` and the payment entry in
  `services/reports.py` read `verified_payments.invoice_id`, always NULL since 0165: stream 08
  deletes them.
- `GET /api/fines/` rows gain `remaining_cents` (05 fix-up); stream 08's `remaining_by_invoice`
  can replace that implementation.
- Test factories: `member_factory(role="officer")` (tests/treasury and tests/auth conftest) now
  also writes the `member_roles` row. A test that wants a column-only officer sets the column
  with `UPDATE members SET role='officer'`.
- Migration numbers taken outside the README ranges: 0203 (02), 0204 (03), 0205 reserved (03
  fixes). Wave 2 keeps 0176–0194 as planned.
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
- `run-stream.sh <id>` launches an external-CLI stream (edit the model flags for Sol/Gemini).
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
01 ≈170k and 03 ≈260k, Fable agents 05 ≈365k and 06 ≈310k, Opus 05 fix-up in flight.
External CLIs are not Claude usage. To spend less Claude: dispatch implementation to
Sol/Gemini via `run-stream.sh`, review with the other CLI, and keep Opus for the two
things that need it (orchestrator judgement calls, and streams where a CLI fails twice).
