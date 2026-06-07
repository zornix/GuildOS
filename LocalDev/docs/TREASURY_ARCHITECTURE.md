# Treasury Service — Architecture

> Durable design reference for the Treasury subsystem (member dues/fines, payments,
> expenses, adjustments, refunds, and reporting). This is the consolidated successor
> to the `treasury-v1-*.md` build-time planning files, which have been removed now that
> the service is complete. For build status the source of truth is the test suite
> (`tests/treasury/`, 115 tests).

Last updated: 2026-06-07

---

## 1. Where it lives

Treasury mounts at `/api/treasury` (one `include_router` call in `api/index.py`). The
package is self-contained under `api/treasury/`:

```
api/treasury/
  core/         # deep domain primitives (no I/O)
    money.py        # Money — integer-cents value object; rejects float/bool
    clock.py        # Clock protocol, SystemClock, FakeClock
    ledger.py       # LedgerWriter + EntryType enum
    audit.py        # AuditLogger + AuditAction enum
    balance.py      # BalanceEngine — the one shared cross-chunk module
    rebuild.py      # RebuildEngine — shadow reconstruction + drift report
    idempotency.py  # idempotency-key convention helpers
  db/
    rpc.py          # call_rpc(name, params, *, sb) — the only sanctioned multi-write path
    session.py      # get_treasury_db() -> service-role client
  services/     # one thin module per operation (invoices, payments, balance,
                #   expenses, adjustments, refunds, reports, rebuild)
  api/          # FastAPI sub-routers, append-only included by router.py
  auth.py       # require_capability(cap) dependency
  notifications.py  # message_outbox enqueue (transactional outbox)
```

Money always crosses the wire and is stored as **integer cents** (`BIGINT`). `Money`
rejects raw `float` at construction; the single sanctioned float→cents boundary is
`Money.from_numeric` (via `Decimal(str(v))`), used only by the legacy fines→invoices
import.

---

## 2. The ledger model

`big_ledger` is an **append-only, signed-cents** event log. Money-in is positive,
money-out negative. It is the audit substrate, not the balance source.

**`EntryType`** (DB CHECK): `INVOICE_CREATED, PAYMENT_RECEIVED, EXPENSE_APPROVED,
EXPENSE_REVERSED, ADJUSTMENT_CREATED, REFUND_ISSUED, CANCEL_INVOICE`.

A DB trigger blocks every `DELETE`, and the only permitted `UPDATE` is a status flip
`active → invalidated`. Reversals are modelled by appending a new row whose
`reverses_entry_id` points at the original — never by mutating history.

`audit_logs` is likewise append-only. **`AuditAction`** (DB CHECK): `CREATE_INVOICE,
VERIFY_PAYMENT, REJECT_PAYMENT, CREATE_EXPENSE, INVALIDATE_EXPENSE, CREATE_ADJUSTMENT,
CANCEL_INVOICE, ISSUE_REFUND, REBUILD`. The enum is frozen: submissions and
adjustment-approvals deliberately reuse existing actions rather than widen it.

---

## 3. The mutation path: RPCs are the only atomic writer

Every multi-row write goes through a `tr_<op>` plpgsql function called via
`call_rpc(...)`. Reads and single-row writes use the `sb.table(...)` builder directly.

Each RPC:

- takes args prefixed `p_`, always including `p_chapter_id uuid` and (where retryable)
  `p_idempotency_key text DEFAULT NULL`;
- runs in one server-side transaction and `RAISE`s on any failure → full rollback
  (this is what makes the operation atomic; proven by `tr_test_atomic_rollback`);
- returns `JSONB` (`to_jsonb(row)`);
- short-circuits replays via `idempotency_keys(chapter_id, operation, key, result_id, result)`.

| Operation | RPC(s) |
|-----------|--------|
| Receivables | `tr_create_invoice`, `tr_bulk_create_invoices`, `tr_submit_payment`, `tr_cancel_invoice` |
| Payment review | `tr_verify_payment`, `tr_reject_payment` |
| Expenses | `tr_create_expense`, `tr_invalidate_expense` |
| Adjustments / refunds | `tr_create_adjustment`, `tr_approve_adjustment`, `tr_issue_refund` |

---

## 4. Balances are computed from operational tables, never from the ledger

`BalanceEngine` reads only the operational tables and writes only the
`member_finance_accounts` cache. It never reads `big_ledger`. This independence is what
lets the rebuild engine cross-check the two.

- **Member:** `current = owed − paid + member_adjustments(active) + member_refunds(active)`;
  `outstanding = max(0, current)` (a negative `current` is a credit / overpayment).
  `owed` = non-cancelled invoice amounts; `paid` = Σ verified payments.
- **Chapter:** `chapter_balance = verified_in − active_expenses + chapter_adjustments(active) − active_refunds`.

Only **active** adjustments/refunds count. A **pending** (over-threshold) adjustment has
no ledger row and no balance effect until a second officer activates it; an
**invalidated** refund is excluded.

---

## 5. Authorization & tenant isolation

Two independent layers:

1. **Capability grants** (`treasury_grants`) checked by the `require_capability(cap)`
   FastAPI dependency. Capabilities: `treasury:read, invoice:create, payment:review,
   expense:create, adjustment:create, refund:create, rebuild:run`. Officers are seeded
   all seven.
2. **Chapter scoping.** Routes resolve `chapter_id` from the authenticated member's DB
   record (`get_current_user`), **never** from the request body. Every RPC re-scopes its
   target rows with `WHERE ... AND chapter_id = p_chapter_id`.

RLS is enabled on the treasury tables with `SELECT` policies gated on
`treasury_has_capability(...)`; writes flow through the service-role client (which
bypasses RLS) via the RPCs, so the RPC bodies carry the integrity checks RLS cannot.

**Tenant-integrity guards** (migration `0080`): because the write path runs as
service-role, the RPCs explicitly verify that a body-supplied `member_id`/`invoice_id`
belongs to the caller's chapter before moving anything:

- `tr_create_invoice` / `tr_bulk_create_invoices` / `tr_create_adjustment` reject a
  `member_id` that is not a member of `p_chapter_id` (a NULL `member_id` on an
  adjustment is a chapter-level adjustment and is allowed);
- `tr_submit_payment` rejects an invoice whose `member_id` is not the submitter.

---

## 6. Governance controls

- **Two-officer sign-off on large adjustments.** `tr_create_adjustment` takes
  `p_threshold_cents` (service constant `LARGE_ADJUSTMENT_THRESHOLD_CENTS = 50000`, `0`
  disables). An adjustment with `abs(delta) >= threshold` is created `status='pending'`
  with no ledger entry; a second officer activates it via `tr_approve_adjustment`, which
  `RAISE`s if the approver is the originating officer and appends the deferred
  `ADJUSTMENT_CREATED` entry at activation.
- **Double-verify safety.** `tr_verify_payment` takes `FOR UPDATE` on the submission and
  relies on a `UNIQUE(submission_id)` backstop on `verified_payments`, so under
  concurrency at most one verified payment per submission can exist.
- **Refund cap.** `tr_issue_refund` caps aggregate active refunds at the source verified
  payment's amount; refunds are corrected by invalidation, never deletion.

---

## 7. Invariants (enforced + tested)

1. No hard deletes (triggers on `big_ledger`, `audit_logs`, `finance_adjustments`, `refunds`).
2. Balances are reconstructable from operational tables (the rebuild engine).
3. Balances are independent of the ledger.
4. Ledger and audit log are append-only.
5. No money moves before approval (a pending submission writes no ledger row).
6. Receipts are immutable.
7. Every money-moving action is audited.
8. Multi-write operations are atomic (RPC rollback).
9. Retries are idempotent (idempotency keys).
10. Rebuild parity: a reconstruction equals live state on a consistent DB.

---

## 8. Rebuild & drift detection

`RebuildEngine.rebuild(chapter_id, *, apply_repairs=False)` rebuilds the ledger multiset
and member/chapter balances from operational tables, diffs them against live
`big_ledger` (status `active`) and `member_finance_accounts`, and returns a
`RebuildReport(reconstructed_ledger, ledger_drift, balance_drift, is_clean, …)`.

Ledger drift is **reported, never repaired** (append-only). `apply_repairs=True` performs
the one and only write it is allowed — `BalanceEngine.recompute_all`, which rewrites the
balance cache. `PAYMENT_RECEIVED` is diffed on `(type, amount, member)` rather than source
table so historical migrated fines don't read as drift; pending adjustments are excluded.
Exposed as `POST /api/treasury/rebuild` (gated `rebuild:run`).

---

## 9. Notifications (transactional outbox)

`message_outbox` is the single notification surface. Four event types:
`INVOICE_ISSUED, PAYMENT_APPROVED, PAYMENT_REJECTED, REFUND_ISSUED`, each with a
`dedup_key = "{event_type}:{target_id}"` under a UNIQUE index → exactly-once. External
dispatch is gated by `MESSAGE_DELIVERY_MODE` (default `dry_run`, where rows persist
`status='pending'`). Every service `notify_*` call threads the caller's `sb` so the
outbox row is written in the same DB/transaction as the operation it describes.

---

## 10. Migrations

`migrations/000N_*.sql`, run once each by `scripts/migrate_db.py` (tracked in
`schema_migrations`, idempotent DDL). Treasury occupies `0005`–`0080`; the first line of
each file names its owning chunk. Because the runner applies a file only once, an
already-applied function is changed by adding a **new** migration that
`CREATE OR REPLACE`s it (e.g. `0080` adds the tenant guards) — never by editing an
applied file.

---

## 11. Endpoint surface

```
POST /invoices                         POST /expenses
POST /invoices/bulk                    POST /expenses/{id}/invalidate
POST /invoices/{id}/cancel             GET  /balance
POST /payments/submissions             GET  /members/{id}/balance
GET  /payments/submissions             POST /adjustments
POST /payments/submissions/{id}/verify POST /adjustments/{id}/approve
POST /payments/submissions/{id}/reject POST /refunds
GET  /payments/receipts/{id}           GET  /dashboard
GET  /members/{id}/statement           GET  /report?period=YYYY-MM&dataset=…
POST /rebuild?apply_repairs=…
```
