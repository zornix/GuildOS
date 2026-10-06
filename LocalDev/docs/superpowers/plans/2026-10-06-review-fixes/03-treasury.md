# Plan 03 — Treasury Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** refunds reverse the right allocations, frozen refund columns include `member_id`, idempotency conflicts are 409s, and refund/verify can't deadlock.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §03.
**Migrations:** 0207–0209 (use what you need, in order; unused numbers go back to the orchestrator in your report).

**Allowed files:** `migrations/0207_*.sql`–`0209_*.sql`, `api/treasury/api/payments.py`, `tests/treasury/*` (new files plus the two named in Task 5). DB functions you own for replacement: the refund RPC whose reversal loop lives in `migrations/0167_refund_reopens_invoice.sql` (confirm the live name in `fn-index.txt` — last definition wins) and the `refunds_freeze` trigger function from `migrations/0168_freeze_money_columns.sql`.

## Task 1 — RV-03-1 (P2): a refund can reopen a paid invoice while the money sits on a cancelled one

`migrations/0167_refund_reopens_invoice.sql:68-83`: the reversal loop ignores invoice status, and allocations created in the same `now()` are ordered by uuid. So reversing can pull cents off a **paid** invoice (reopening it) while credit still sits on a **cancelled** invoice.

- [ ] Failing test first, in a new `tests/treasury/test_refund_reversal_order.py` (own chapter fixture): member with invoice A **paid** and invoice B **cancelled** holding an allocation from the same payment; issue a refund sized to B's allocation; assert A stays `paid` and the reversal row targets B. Must fail on the untouched branch.
- [ ] `migrations/0207_refund_reversal_order.sql`: `CREATE OR REPLACE` of the live refund function (0167 body as base). Change only the reversal ordering: allocations on **cancelled invoices first**, then **newest first**, with a stable tiebreak (`id`) instead of bare uuid ordering.
- [ ] While you are in this body, also fix RV-03-4 (Task 4) — same function, one replacement.
- [ ] Apply, update checksums, run the test → PASS. Checkpoint: `python3 -m pytest tests/treasury/test_refund_reversal_order.py -q`.

## Task 2 — RV-03-2 (P2): one UPDATE can move a refund to another member

`migrations/0168_freeze_money_columns.sql:38`: the `refunds_freeze` trigger freezes money columns but not `member_id`, while `api/treasury/core/balance.py:128-136` sums refunds **by member_id** — so an UPDATE can silently move money between members' balances.

- [ ] Failing test first (`tests/treasury/test_refund_reversal_order.py` or a new `test_refund_freeze.py`): create a refund, `UPDATE refunds SET member_id = <other member in same chapter>` with the superuser test connection → expect no exception today (reproduces), then after the fix expect the trigger to raise.
- [ ] `migrations/0208_freeze_refund_member.sql`: `CREATE OR REPLACE` the freeze trigger function with `member_id` added to the frozen columns (base: 0168 live body). Idempotent; no new trigger objects needed if you only replace the function — otherwise `DROP TRIGGER IF EXISTS` first.
- [ ] Apply, update checksums, test → PASS.

## Task 3 — RV-03-3 (P2): reused Idempotency-Key with a changed body returns 500, not 409

`api/treasury/api/payments.py:207-235`: `tr_record_payment` (0205) raises its `request_hash` mismatch error, and the route lets it surface as a 500.

- [ ] Failing route-level test first (dependency-override client, own chapter): `POST /payments/record` twice with the same `Idempotency-Key` but a changed amount → assert 409 and a fixed message with no raw database text. Today it 500s.
- [ ] Fix in `payments.py`: catch the RPC's hash-mismatch error (match its stable message fragment) and map to `HTTPException(409, …)` — fixed English, no `f"{exc}"`.
- [ ] Checkpoint: `python3 -m pytest tests/treasury/ -q -k "idempot or refund"`.

## Task 4 — RV-03-4 (P3): refund and verify lock invoices in opposite orders

0167's refund loop vs 0166's verify path lock a member's invoices in different orders → deadlock window. Fixed inside Task 1's function replacement: make the refund function take the member's invoice locks in the **same order 0166 uses** (`ORDER BY id`) before reversing. No separate migration (0209 then stays unused — report it back).

- [ ] Covered by Task 1's migration; existing refund/verify tests stay green: `python3 -m pytest tests/treasury/ -q -k "refund or verify"`.

## Task 5 — RV-03-5 (P3): tests re-run the 0165 data block across the whole shared DB

- [ ] `tests/treasury/test_single_coverage.py:24-28, 73, 145-146` and `tests/treasury/test_chunkG_rebuild_hardening.py:283`: scope the re-run/backfill SQL to the test's own `chapter_id` instead of the whole database. Behaviour asserted stays the same; these are shared-DB hygiene fixes.
- [ ] Checkpoint: `python3 -m pytest tests/treasury/test_single_coverage.py tests/treasury/test_chunkG_rebuild_hardening.py -q`.

## Final checkpoint

- [ ] `python3 -m pytest tests/treasury/ -q` — paste the final count line.
