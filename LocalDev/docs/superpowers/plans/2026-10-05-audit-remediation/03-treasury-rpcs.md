# 03 · Treasury RPCs: one coverage mechanism, refunds reopen, pay the picked invoice

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `03-treasury-rpcs` · **Wave:** 1 · **Agent:** Claude Opus 5.5 (worktree agent) · **Branch:** `fix/audit-03-treasury-rpcs`
**Findings:** F-029, F-030, F-031, F-032, F-058, F-070, plus the server half of F-014 · **Not in scope:** F-027 (decision D2: self-approval stays as is)
**Migrations:** `0165` … `0170` (one per task that needs SQL; unused numbers stay unused)
**Goal:** invoice coverage lives only in `payment_allocations`; a refund reopens the invoice it covered; a payment goes to the invoice the member picked; amounts on money rows cannot be edited in place.
**Architecture:** every change is a guard or a step added inside an existing `tr_*` function, or a new trigger. No logic moves out of SQL into Python (report §14). Python changes are limited to which RPC a route calls, error mapping, and `core/rebuild.py`.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-029, F-030, F-031, F-032, F-058, F-070; Appendix C.3 (RPC behaviour); decisions D2, D3, D7, D10, D11 in `00-README.md`.

## Global constraints

- Allowed files: `migrations/0165_*.sql` … `0170_*.sql`, `api/treasury/api/payments.py`, `api/treasury/api/refunds.py`, `api/treasury/api/invoices.py` (error mapping for Task 6 only), `api/treasury/services/payments.py`, `api/treasury/services/refunds.py`, `api/treasury/services/invoices.py` (Task 6 only), `api/treasury/core/rebuild.py`, `tests/treasury/**`.
- DB functions you own this wave: `tr_verify_payment`, `tr_verify_payment_v2`, `tr_reallocate_payment`, `tr_issue_refund`, `tr_invoice_remaining_cents`, `tr_bulk_create_invoices`, and the new `tr_record_payment`. `CREATE OR REPLACE` with the exact live signature and return shape (`fn-index.txt` says where the live body is). Do not replace any other function; `tr_create_adjustment` and `tr_approve_adjustment` are deliberately untouched.
- Do not change `BalanceEngine`'s formula (`api/treasury/core/balance.py`), `Money`, entry-type or audit-action enums, the outbox, or any route path.
- Every data-changing statement in a migration must be re-runnable (`ON CONFLICT DO NOTHING`, `WHERE … IS NOT NULL`, `IF NOT EXISTS`).
- Run `python3 -m pytest tests/treasury -q` after each task. Run the full suite once at the end.

## Review focus

1. After the Task 1 data migration, every member's `BalanceEngine` figures are identical to before (coverage moved, money did not).
2. A cancelled invoice never returns to `unpaid`/`partially_paid`/`paid` through any path touched here.
3. A refund larger than what is still allocated from that payment (the rest was unallocated credit) reverses only what exists and does not fail.
4. A targeted payment larger than the picked invoice sends the surplus oldest-first; a targeted payment whose invoice is already paid or cancelled falls back to oldest-first entirely.
5. The freeze triggers (Task 5) must not block any statement an existing `tr_*`, `at_*` or `ch_*` function performs. The full suite is the check.

---

### Task 1: F-029 — coverage only through allocations

Today a v1 verification and every paid fine migrated by `0012` store coverage in `verified_payments.invoice_id`; v2 stores it in `payment_allocations`. Reallocating a v1 payment counts its cents twice.

**Files:** `migrations/0165_single_coverage.sql`, `api/treasury/api/payments.py:57-70`, `api/treasury/services/payments.py`, `tests/treasury/test_single_coverage.py` (new), existing `tests/treasury/test_chunkC_payments.py`

- [ ] **Step 1: reproduce.** Test `test_reallocating_a_directly_covered_payment_does_not_pay_two_invoices`: with `cursor`, create invoices A and B (same member, same amount) and a `verified_payments` row with `invoice_id = A` the way `0012` did (no allocation rows); mark A paid. Call `tr_reallocate_payment` moving the full amount to B. Assert exactly one of A, B is `paid` afterwards and `tr_invoice_remaining_cents(A)` equals A's full amount. Expected today: FAIL (both paid). If it passes on the untouched branch, report F-029 `NOT_REPRODUCED` and skip to Task 2.
- [ ] **Step 2: migration `0165_single_coverage.sql`.**
  1. Data: for every `verified_payments` row with `invoice_id IS NOT NULL` that has no allocation row for that invoice, insert one `payment_allocations` row (`chapter_id`, `verified_payment_id`, `invoice_id`, `amount_cents = verified_payments.amount_cents`, `note = 'migrated from verified_payments.invoice_id (0165)'`). Then `UPDATE verified_payments SET invoice_id = NULL WHERE invoice_id IS NOT NULL`. Wrap both in a `DO` block that captures, before and after, `SUM` of remaining cents over all non-cancelled invoices (via `tr_invoice_remaining_cents`) and raises if the two totals differ.
  2. `tr_invoice_remaining_cents`: drop the `verified_payments.invoice_id` term so remaining = `amount_cents − tr_net_allocated_cents(invoice)`.
  3. `tr_verify_payment` (v1, live at `0031:11`): replace its body so it validates exactly as today and then performs the same writes as `tr_verify_payment_v2` (simplest: `RETURN tr_verify_payment_v2(…)` with the same arguments, if the signatures line up; keep the v1 name so old callers and tests still resolve). It must no longer set `verified_payments.invoice_id` or write `unpaid_invoices.status` directly.
  4. `tr_reallocate_payment`: add a guard that raises if the payment still has `invoice_id IS NOT NULL` (belt for rows created outside the migration).
- [ ] **Step 3: route.** `POST /payments/submissions/{id}/verify` (`payments.py:57-70`) calls `svc.verify_payment_v2`, same as `/verify-v1`. Keep both paths (frozen URLs). Delete `svc.verify_payment` if nothing else calls it (`grep -rn "verify_payment(" api tests`).
- [ ] **Step 4: tests.** Step 1 test passes. Add `test_migrated_direct_coverage_keeps_balances`: build one legacy-shaped paid invoice, record `BalanceEngine` figures, run the data statements of `0165` again (they must be no-ops), assert figures unchanged and the invoice still `paid`. Update `test_chunkC_payments.py` assertions that expect `verified_payments.invoice_id` to be set after verify: they now expect an allocation row. Add `test_verify_does_not_resurrect_a_cancelled_invoice`: submit against an invoice, void it, verify; invoice stays `cancelled`.
- [ ] **Step 5: commit** — `fix(treasury): store invoice coverage only in payment_allocations`

---

### Task 2: F-032 — pay the invoice the member picked (decision D7)

**Files:** `migrations/0166_targeted_allocation.sql`, `tests/treasury/test_v1_allocation.py:104-117`

- [ ] **Step 1: flip the test.** `test_verify_v2_works_for_invoice_targeted_submissions` currently asserts the older invoice gets the money. Rewrite it: submit against `inv_b` for exactly `inv_b`'s amount; after verify, `inv_b` is `paid` and the older `inv_a` is untouched. Add `test_targeted_surplus_flows_oldest_first` (pay `inv_b` amount + 1000: `inv_b` paid, `inv_a` gets 1000) and `test_target_already_closed_falls_back_to_oldest_first` (target is cancelled before verify: all cents go oldest-first, none to the cancelled invoice).
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.** In `tr_verify_payment_v2` (live at `0124:124`), before the oldest-first loop: if `v_submission.invoice_id IS NOT NULL` and that invoice belongs to the same member and chapter and its status is `unpaid` or `partially_paid`, allocate `LEAST(remaining payment cents, tr_invoice_remaining_cents(target))` to it and refresh its status; then run the existing loop for whatever is left, skipping the target. Nothing else in the function changes.
- [ ] **Step 4: run, expect PASS; commit** — `fix(treasury): apply a payment to the invoice it was submitted against first`

---

### Task 3: F-030 — a refund reopens what it covered (decision D3)

**Files:** `migrations/0167_refund_reopens_invoice.sql`, `tests/treasury/test_chunkE_adjustments_refunds.py`

- [ ] **Step 1: failing tests.** `test_full_refund_reopens_the_invoice`: pay a 10000-cent invoice in full through submit + verify, refund 10000; the invoice is `unpaid`, `tr_invoice_remaining_cents` is 10000, and the member's outstanding is 10000. `test_partial_refund_makes_invoice_partially_paid` (refund 4000 → `partially_paid`, remaining 4000). `test_refund_of_unallocated_credit_changes_no_invoice` (payment of 15000 against a 10000 invoice, refund 5000: invoice stays `paid`). `test_refund_does_not_touch_cancelled_invoice`.
- [ ] **Step 2: run, expect the first two to FAIL.**
- [ ] **Step 3: implement.** In `tr_issue_refund` (live at `0052:8`), after the refund row and ledger row are written: let `v_credit` = the payment's `amount_cents` minus its net allocated cents (unallocated credit). Refund cents consume `v_credit` first. For the rest, walk that payment's live allocations newest first; for each, append a reversal row (`reverses_allocation_id` set, same `invoice_id`, positive `amount_cents`, the way `tr_reallocate_payment` writes reversals) for `LEAST(what is left, that allocation's net amount)`, then call `tr_refresh_invoice_status` on that invoice. Match `tr_reallocate_payment`'s reversal convention exactly so `tr_net_allocated_cents` nets it out. Account for earlier refunds on the same payment: the cents to reverse now = this refund's cents minus whatever credit is still unconsumed after earlier refunds.
- [ ] **Step 4: run `tests/treasury -q`, expect PASS; commit** — `fix(treasury): refunds reverse allocations so the invoice reopens`

---

### Task 4: F-058 — rebuild keys payments on their source

**Files:** `api/treasury/core/rebuild.py:23-27, 126-161`, `tests/treasury/test_chunkG_rebuild_hardening.py`

- [ ] **Step 1: failing test.** `test_missing_and_stray_payment_rows_do_not_cancel_out`: a member with two verified payments of 2500, each with its ledger row; invalidate one ledger row (`UPDATE big_ledger SET status='invalidated'`, allowed by the trigger) and insert a stray active `PAYMENT_RECEIVED` of 2500 for the same member pointing at a random `source_id`. `rebuild()` must report drift (`is_clean` false). Today it reports clean.
- [ ] **Step 2: implement.** `_ledger_key` includes `source_id` for `PAYMENT_RECEIVED` like every other type. Keep the 0012 exception narrow: a live row with `source_table = 'unpaid_invoices'` is matched to the reconstructed payment whose invoice that is (after Task 1 the link is the payment's migrated allocation row, note `'migrated from verified_payments.invoice_id (0165)'`, or the original `0012` relation; read `migrations/0012_fines_to_invoices_migration.sql:40-51` and pick the lookup that works for rows created by 0012). Update the "Deviation #3" comment to describe the alias.
- [ ] **Step 3: run the rebuild tests, expect PASS; commit** — `fix(treasury): rebuild matches payment ledger rows by source`

---

### Task 5: F-031 — amounts on money rows are frozen (decision D10)

The ledger stays a shadow (report §10). What changes: the rows balances are computed from can no longer have their amount or owner edited in place.

**Files:** `migrations/0168_freeze_money_columns.sql`, `tests/treasury/test_frozen_amounts.py` (new)

- [ ] **Step 1: failing tests**, one per table, each doing a direct `UPDATE` through `cursor` and expecting `psycopg2.Error` matching `frozen`: `verified_payments.amount_cents`, `verified_payments.member_id`, `finance_adjustments.delta_cents`, `refunds.amount_cents`, `unpaid_invoices.amount_cents`, `unpaid_invoices.member_id`. Plus two that must still succeed: `unpaid_invoices.status` change and `finance_adjustments` `pending → active`.
- [ ] **Step 2: implement.** One trigger function:

```sql
CREATE OR REPLACE FUNCTION tr_freeze_columns() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_col TEXT;
BEGIN
    FOREACH v_col IN ARRAY TG_ARGV LOOP
        IF to_jsonb(NEW) -> v_col IS DISTINCT FROM to_jsonb(OLD) -> v_col THEN
            RAISE EXCEPTION 'frozen: %.% cannot change after insert', TG_TABLE_NAME, v_col;
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;
```

and one `BEFORE UPDATE` trigger per table (`DROP TRIGGER IF EXISTS` first): `verified_payments` (`amount_cents`, `member_id`, `chapter_id`), `finance_adjustments` (`delta_cents`, `member_id`, `chapter_id`), `refunds` (`amount_cents`, `verified_payment_id`, `chapter_id`), `unpaid_invoices` (`amount_cents`, `member_id`, `chapter_id`). Before choosing the column lists, `grep -rnE "UPDATE (verified_payments|finance_adjustments|refunds|unpaid_invoices)" migrations/` and remove from the list any column a live function legitimately updates; report what you removed and why.
- [ ] **Step 3: run `tests/treasury tests/attendance tests/chapters -q`, expect PASS; commit** — `feat(treasury): freeze amount and owner columns on money rows`

---

### Task 6: F-070 — a reused dues-run key with a different payload is rejected (decision D11)

Scope is deliberately one RPC: `tr_bulk_create_invoices`, the only one whose key the UI can reuse with an edited body.

**Files:** `migrations/0169_idempotency_request_hash.sql`, `api/treasury/services/invoices.py` and `api/treasury/api/invoices.py` (error mapping), `tests/treasury/test_dues_run.py`

- [ ] **Step 1: failing test.** `test_same_key_different_items_is_rejected`: run a dues run with key K and amount 10000; run again with key K and amount 12000; expect HTTP 409 (or, at RPC level, an error matching `idempotency_key_reused`). `test_same_key_same_items_replays` still returns the first result with `_created: false` behaviour unchanged.
- [ ] **Step 2: implement.** `ALTER TABLE idempotency_keys ADD COLUMN IF NOT EXISTS request_hash TEXT;`. In `tr_bulk_create_invoices` (live at `0158:8`): compute `v_hash := md5(p_items::text || '|' || COALESCE(<every other payload argument>::text, ''))` (read the signature; include every argument except the key and the actor). On replay: if the stored `request_hash` is not null and differs, `RAISE EXCEPTION 'idempotency_key_reused: this key was used with a different request'`; otherwise return the stored result as today. On first use, store the hash. Map the error to `HTTPException(409, "This request was already submitted with different details. Start a new one.")` where the dues-run route handles RPC errors.
- [ ] **Step 3:** add a comment above the column: `-- ponytail: only tr_bulk_create_invoices checks request_hash and keys never expire; extend per RPC and add a purge job when the table matters.`
- [ ] **Step 4: run, expect PASS; commit** — `fix(treasury): reject a reused dues-run idempotency key with a different payload`

---

### Task 7: F-014 (server half) — an officer records a payment in one step (decision D1)

The Finance tab's "record payment" and "mark fine paid" buttons save nothing today because no endpoint lets an officer record money for a member. Stream 05 wires the UI to the route below; the request and response shapes are a cross-stream contract (`00-README.md`, "Contracts").

**Files:** `migrations/0170_record_payment.sql`, `api/treasury/api/payments.py`, `api/treasury/services/payments.py`, `tests/treasury/test_record_payment.py` (new)

**Interfaces (produced):**

```
POST /api/treasury/payments/record        requires treasury:payment:verify
Header: Idempotency-Key (optional)
Body:   { "member_id": str, "amount_cents": int > 0,
          "method": "venmo"|"zelle"|"cash"|"bank_transfer"|"check",
          "invoice_id": str | null, "reference": str | null }
200:    the same JSON tr_verify_payment_v2 returns today (verified payment + allocations)
404:    member or invoice not in the caller's chapter
409:    invoice is cancelled or already paid
```

- [ ] **Step 1: failing tests.** `test_record_payment_against_invoice_pays_it` (officer records the invoice's amount with `invoice_id`; invoice `paid`, one `verified_payments` row, one `payment_submissions` row `approved`, `audit_logs` rows carry the officer as actor). `test_record_payment_without_invoice_allocates_oldest_first`. `test_record_payment_is_atomic` (pass an `invoice_id` that belongs to another member: the call fails and no `payment_submissions` row exists for the target member afterwards). `test_record_payment_idempotent` (same key twice → one verified payment). `test_record_payment_requires_permission` (plain member → 403). `test_record_payment_cross_chapter_member_404`.
- [ ] **Step 2: implement the RPC.** `tr_record_payment(p_chapter_id UUID, p_member_id UUID, p_amount_cents BIGINT, p_method TEXT, p_actor_id UUID, p_invoice_id UUID DEFAULT NULL, p_reference TEXT DEFAULT NULL, p_idempotency_key TEXT DEFAULT NULL) RETURNS JSONB`: validate the member is in the chapter; call `tr_submit_payment` when `p_invoice_id` is given, else `tr_submit_balance_payment`, for `p_member_id`; then call `tr_verify_payment_v2` on the new submission with `p_actor_id`; return its result. One plpgsql function, so both steps commit or neither does. Derive the inner idempotency keys from `p_idempotency_key` (`|| ':submit'`, `|| ':verify'`) so a replay is a no-op. Read the three live signatures first (`fn-index.txt`).
- [ ] **Step 3: route + service.** Add `RecordPaymentBody` and `POST /payments/record` next to the other V1 routes; the service calls `call_rpc("tr_record_payment", …)`, then refreshes the member's balance cache and enqueues the same notification `verify_payment_v2` does today (reuse that code path; do not duplicate it).
- [ ] **Step 4: run `tests/treasury -q`, expect PASS; commit** — `feat(treasury): officers can record a payment for a member in one step`

---

### Task 8: full suite

- [ ] `python3 -m pytest -q` from `LocalDev/`. Report the final count line verbatim and every pre-existing test you changed, with the reason.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
