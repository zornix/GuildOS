# Treasury Service — Architecture

> Durable design reference for the Treasury subsystem (member dues/fines, payments,
> expenses, adjustments, refunds, and reporting). This is the consolidated successor
> to the `treasury-v1-*.md` build-time planning files, which have been removed now that
> the service is complete. For build status the source of truth is the test suite
> (`tests/treasury/`).

Last updated: 2026-10-06

---

## 1. Where it lives

Treasury mounts at `/api/treasury` (one `include_router` call in `api/index.py`). The
package is self-contained under `api/treasury/`:

```
api/treasury/
  core/         # money primitives, balance computation, drift detection
    money.py        # Money — integer-cents value object; rejects float/bool
    clock.py        # Clock protocol, SystemClock, FakeClock
    ledger.py       # EntryType enum
    audit.py        # AuditAction enum
    balance.py      # BalanceEngine — the one shared cross-chunk module
    rebuild.py      # RebuildEngine — shadow reconstruction + drift report
  services/     # one thin module per operation (invoices, payments, balance,
                #   expenses, adjustments, refunds, reports, rebuild, remaining)
  api/          # FastAPI sub-routers, append-only included by router.py
  notifications.py  # post-commit message_outbox enqueue
```

Money always crosses the wire and is stored as **integer cents** (`BIGINT`). `Money`
rejects raw `float` at construction; the single sanctioned float→cents boundary is
`Money.from_numeric`, called only by the unused compatibility DTO
`FineToInvoice` (`api/treasury/api/schemas.py`), which stringifies its float input
before conversion. Live fine issuance passes integer cents to `tr_issue_event_fines`.

---

## 2. The ledger model

### What the ledger is

Balances are computed from the operational tables (`unpaid_invoices`, `verified_payments`, `finance_adjustments`, `refunds`). Amount and owner columns on those rows are frozen by trigger (migration 0168). `big_ledger` is an append-only shadow log; `core/rebuild.py` reports ledger and balance-cache drift. It is read-only by default and never repairs the ledger. With `apply_repairs=true`, it recomputes the balance cache.

`big_ledger` is an **append-only, signed-cents** event log. Money-in is positive,
money-out negative. It is the audit substrate, not the balance source.

**`EntryType`** (DB CHECK): `INVOICE_CREATED, PAYMENT_RECEIVED, EXPENSE_APPROVED,
EXPENSE_REVERSED, ADJUSTMENT_CREATED, REFUND_ISSUED, CANCEL_INVOICE`.

A DB trigger blocks every `DELETE`, and the only permitted `UPDATE` is a status flip
`active → invalidated`. Reversals are modelled by appending a new row whose
`reverses_entry_id` points at the original — never by mutating history.

`audit_logs` is likewise append-only. **`AuditAction`** (Python enum): `CREATE_INVOICE,
VERIFY_PAYMENT, REJECT_PAYMENT, CREATE_EXPENSE, INVALIDATE_EXPENSE, CREATE_ADJUSTMENT,
CANCEL_INVOICE, ISSUE_REFUND, REBUILD`. The enum is frozen: submissions and
adjustment-approvals deliberately reuse existing actions rather than widen it.

---

## 3. The mutation path

Trust-boundary treasury mutations go through `tr_*` plpgsql functions called via
`call_rpc(...)`. Other multi-statement writes use the owner connection through
`PostgresClient.transaction()`; reads use the `sb.table(...)` builder or SQL.
The app connects as the table owner in every environment.

Command RPCs:

- take args prefixed `p_`, including `p_chapter_id uuid` and (where supported)
  `p_idempotency_key text DEFAULT NULL`;
- run in one server-side transaction and `RAISE`s on any failure → full rollback
  (this is what makes the operation atomic; proven by `tr_test_atomic_rollback`);
- return `JSONB` (a row or an operation-specific object);
- short-circuit replays when an idempotency key is supplied via `idempotency_keys(chapter_id, operation, key, result_id, result)`.

| Operation | RPC(s) |
|-----------|--------|
| Receivables | `tr_create_invoice`, `tr_create_invoice_v2` (line items), `tr_bulk_create_invoices`, `tr_cancel_invoice`, `tr_void_invoice` |
| Payment submission / review | `tr_submit_payment`, `tr_submit_balance_payment`, `tr_verify_payment` (delegates to v2), `tr_verify_payment_v2`, `tr_reject_payment` |
| Officer payment / allocation | `tr_record_payment`, `tr_reallocate_payment` |
| Event fines | `tr_issue_event_fines`; attendance paths use `at_void_open_fines` to void open fines |
| Expenses | `tr_create_expense`, `tr_invalidate_expense` |
| Adjustments / refunds | `tr_create_adjustment`, `tr_approve_adjustment`, `tr_issue_refund` |

Allocation/status helpers are `tr_net_allocated_cents`, `tr_invoice_remaining_cents`
and `tr_refresh_invoice_status`. Invoice remaining cents use allocations and their
reversals, rather than `verified_payments.invoice_id`. Bulk invoices (0169) and
officer-recorded payments (0205) reject idempotency-key reuse with a changed payload.
Refunds consume unallocated credit first, then reverse cancelled-invoice coverage
before reopening paid invoices. Invoice locks follow `(created_at, id)` ascending;
reversal order is cancelled first, allocation creation descending, then invoice
creation/id descending and allocation id descending (0217).

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

The `member_balances` CSV computes every balance column from operational tables
in one SQL statement, starting from chapter members so members without cache rows
are included; members without activity have zero balances. It is a current snapshot, not period-bound.
Dashboard `recent_payments` includes each submission's `proof_ref` and method.

---

## 5. Authorization & tenant isolation

Two independent layers:

1. **RBAC permissions** checked by `api.rbac.auth.require_permission`.
   Permissions come from `member_roles` plus an implicit `member` baseline;
   `members.role` grants no authority. Payment review uses
   `treasury:payment:verify`; rebuild uses `treasury:rebuild:run`.
2. **Chapter scoping.** Routes resolve `chapter_id` from the authenticated member's DB
   record (`get_current_user`), **never** from the request body. Every RPC re-scopes its
   target rows with `WHERE ... AND chapter_id = p_chapter_id`.

RLS is enabled on the treasury tables with `SELECT` policies gated on
`treasury_has_capability(...)`; the app connects as the table owner and
bypasses RLS; writes flow through RPCs, so the RPC bodies carry the integrity checks RLS cannot.

**Tenant-integrity guards** (migration `0080`): because the write path runs as
the table owner, the RPCs explicitly verify that a body-supplied `member_id`/`invoice_id`
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
Exposed as `POST /api/treasury/rebuild` (gated `treasury:rebuild:run`).

---

## 9. Notifications (outbox)

Treasury lifecycle notifications use `message_outbox` with event types
`INVOICE_ISSUED`, `PAYMENT_APPROVED`, `PAYMENT_REJECTED`, and `REFUND_ISSUED`.
Their `dedup_key = "{event_type}:{target_id}"` has a UNIQUE index, so retries
do not enqueue duplicate rows. The helpers enqueue after the money RPC commits.
A real enqueue failure is logged outside a transaction, leaving the money
committed; with a transaction client, the error propagates and rolls back
that transaction.

Enqueue writes `status='pending'`. The cron drain delivers treasury email;
`MESSAGE_DELIVERY_MODE` gates provider calls, and dry-run delivery marks rows
`simulated`. Inline SMS dispatch is also supported:
`api/announcements/services/sms.py::dispatch_send` atomically claims pending
rows before sending them.

---

## 10. Migrations

`migrations/*.sql`, run once each by `scripts/migrate_db.py` (tracked in
`schema_migrations`, idempotent DDL). Treasury starts at `0005` and has later
allocation, fine and review migrations through `0217`. Because the runner applies a file only once, an
already-applied function is changed by adding a **new** migration that
`CREATE OR REPLACE`s it (e.g. `0080` adds the tenant guards) — never by editing an
applied file. After adding a migration, run
`python3 scripts/migration_checksums.py --update`.

| Migrations | Treasury change |
|---|---|
| 0120, 0122–0124 | Line-item invoices; voiding; balance submissions/evidence; allocations and invoice-status refresh |
| 0158 | Bulk dues due dates |
| 0165 | Single coverage; v1 verify delegates to v2; remaining-cents helper |
| 0166 | Targeted allocation before oldest-first allocation; canonical invoice locks |
| 0167 | Refunds reverse allocations and reopen invoices |
| 0168 | Freeze operational money/owner columns |
| 0169 | Bulk-invoice idempotency request hashes |
| 0170 | Officer-recorded payments |
| 0171 | Revoke Supabase API-role privileges (shared boundary) |
| 0196, 0198–0199, 0201 | Event-fine issuance; attendance voiding; fine uniqueness/status guards; skip handled fines |
| 0205 | Reallocation and record-payment guards, tenant checks and request hashes |
| 0207 | Refunds reverse cancelled-invoice coverage first |
| 0208 | Freeze refund member ownership |
| 0209 | Refund invoice locks align with verification lock order |
| 0213 | Fine issuance and attendance serialize with the event attendance lock |
| 0214 | Self check-in voids open fines |
| 0217 | Deterministic refund reversal tiebreak for same-time allocations; latest `tr_issue_refund` body |

This review round added 0206–0217; 0216/0217 refine 0210/0209. There is no 0202
migration. 0215 is the outbox attempt cap, not a treasury mutation migration.

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

Additional routes under `/api/treasury`:

```
POST /invoices/{invoice_id}/void
POST /payments/balance-submissions
POST /payments/submissions/{submission_id}/evidence
GET  /payments/evidence/{evidence_id}
POST /payments/submissions/{submission_id}/verify-v1
POST /payments/submissions/{submission_id}/reject-v1
POST /payments/record
POST /payments/{verified_payment_id}/reallocate
GET  /payments/{verified_payment_id}/allocations
GET  /members/{member_id}/dashboard
```

`verify-v1`/`reject-v1` are what the app calls; `/verify` is a frozen URL with the same behaviour (both run `tr_verify_payment_v2`), and `reject-v1` requires a reason. Payment evidence uploads
are capped at 2 MiB and scoped to the submission's chapter and owner. The report
datasets are `payments`, `invoices`, `expenses`, `member_balances`, and `ledger`.

The separate `/api/fines` router (`api/treasury/api/fines_legacy.py`) exposes
`GET /`, `GET /missed/{event_id}`, `POST /issue`, `POST /{invoice_id}/waive` and
`GET /summary`. Issuance creates flat 2500-cent invoices for eligible unexcused
members after the 24-hour gate through `tr_issue_event_fines`; waiving calls
`tr_void_invoice`. Attendance updates and self check-in void open fine invoices.
