# Treasury audit — invoices, payments, verification, evidence, receipts, reminders

Read-only audit of `LocalDev/` on 2026-10-11 (main @ 80e4f8b). Paths are relative to `LocalDev/`.
**FACT** = read in code. **INFERENCE** = my reading of the code or platform behaviour, not run.

---

## 1. Invoice and payment model

**Tables (FACT)**
| Table | Role | Where |
|---|---|---|
| `unpaid_invoices` | Every receivable (dues/rent/utilities/fine/assessment/manual). **Paid invoices stay in this table**; only `status` changes | migrations/0010:5-21 |
| `payment_submissions` | A member's claim "I paid": `pending → approved / rejected`. `invoice_id` can be NULL (a balance-level claim) | 0010:32-49, 0123:7 |
| `payment_evidence` | Proof bytes as BYTEA. Capped at 2 MiB. Append-only | 0123:14-35 |
| `verified_payments` | Money that was accepted. One per submission (UNIQUE) | 0010:59-73 |
| `receipts` | Immutable record issued **per verified payment** (UNIQUE `verified_payment_id`) | 0030:6-31 |
| `payment_allocations` | Append-only mapping of a payment to invoices. A correction is a reversal row | 0124:23-49 |
| `big_ledger`, `audit_logs` | Append-only shadow log and audit trail | 0005:43-160 |
| `idempotency_keys` | `UNIQUE(chapter_id, operation, key)`, plus `request_hash` from 0169 | 0005:29-39, 0169:12 |

**Status (FACT).** `tr_refresh_invoice_status` (0124:94-121) recomputes `unpaid`, `partially_paid` or `paid` from `tr_invoice_remaining_cents`. Since 0165, remaining cents are calculated from allocations only (0165:1-13). A `cancelled` row is never touched. A refund can reopen a paid invoice (0167). The API maps `unpaid/partially_paid → open`, `cancelled → void` and keeps the raw value in `raw_status` (api/treasury/services/invoices.py:138-182). Python's `remaining_by_invoice` (api/treasury/services/remaining.py:5-21) uses the same allocation-only formula.

**What "paid" means (FACT).** An invoice is paid when its net allocations are at least its amount. No separate "paid invoice" record exists. A "paid invoice" is just an `unpaid_invoices` row with `status='paid'`.

**Idempotency (FACT).** Every `tr_*` RPC accepts `p_idempotency_key`. Only `tr_bulk_create_invoices` (0169) and `tr_record_payment` (0205:157-170) reject a reused key whose payload changed. Keys never expire (0169:11 `ponytail:` note).

**Endpoints a member can call for their own history (FACT)**
- `GET /api/treasury/members/{me}/dashboard`: balance, **pending** submissions and **open invoices only** (`.in_("status", ["unpaid","partially_paid"])`, api/treasury/services/member_dashboard.py:62-67). It also returns the last 10 `big_ledger` rows as `recent_activity` (:90-97). Paid invoices are not included.
- `GET /api/treasury/members/{me}/statement` (api/treasury/api/reports.py:84-110; services/reports.py:219-318): **every non-cancelled invoice, including paid ones, with raw status**, plus every verified payment, active adjustment and active refund, in date order, with totals. Payment entries carry an empty `detail: {}` (services/reports.py:187), so there is no method, reference or receipt id. **The frontend never calls this endpoint** (no match in greekos/src).
- `GET /api/fines/` (api/treasury/api/fines_legacy.py:123-141): fine-kind invoices, own rows only for a non-auditor, **all statuses**, including paid.
- `GET /api/treasury/payments/{vp_id}/allocations`: open to the owner or a reviewer (payments.py:289-311).
- **A member cannot read their own receipt.** `GET /payments/receipts/{id}` requires `treasury:audit:view` (payments.py:24, 314-323), and no endpoint lists receipts or maps a payment to its receipt id.
- **A member cannot see their rejected submissions** (the dashboard returns only `pending`, member_dashboard.py:48-56).

**Officer endpoints (FACT).** `/members/{id}/statement` and `/members/{id}/balance` (`treasury:audit:view`). `/members/{id}/dashboard` (`audit:view` or `payment:verify`). `GET /payments/submissions?status=pending|approved|rejected` (`payment:verify`, reports.py:30-69). `/dashboard` (`budget:view`). `/report?dataset=payments|invoices|ledger…` CSV (`audit:view`).

## 2. Recording and verification

**Who records (FACT)**
- A member self-reports with `POST /payments/submissions`, naming one invoice (api/treasury/api/invoices.py:175-192 → `tr_submit_payment`). It fills `member_id` from the session, and the 0080 guard rejects another member's invoice.
- A member can also submit against their overall balance with `POST /payments/balance-submissions` (payments.py:117-133). **No UI uses this.**
- An officer records a payment with `POST /payments/record` (`treasury:payment:verify`, payments.py:207-235). This is submit and verify in one RPC (0205:139-196).

**Who verifies (FACT).** Only holders of `treasury:payment:verify`, through `/verify-v1` (used by the UI) or the frozen `/verify`. Both call `tr_verify_payment_v2` (payments.py:77-91, 190-204). Rejecting needs the same key. `/reject-v1` makes a reason mandatory (payments.py:238-256).

**On approval (FACT, 0166:9-158)**, all in one transaction:
1. Lock the submission. A replay of an approved submission returns `_created:false`.
2. Insert `verified_payments` with **amount = claimed amount**. The reviewer cannot change the amount.
3. Insert `receipts`. Its `invoice_id` is NULL for v2.
4. Append a `PAYMENT_RECEIVED` row to `big_ledger`.
5. Set the submission to approved.
6. Allocate the payment to the named invoice first, then to open invoices oldest first, calling `tr_refresh_invoice_status` for each.
7. Write `audit_logs` VERIFY_PAYMENT with allocated and leftover cents.

After that, Python recomputes the balance cache. On first creation only, it enqueues `PAYMENT_APPROVED` (services/payments.py:149-163). Officer-recorded payments follow the same path (:166-193).

**On rejection (FACT).** Status changes to `rejected`. **The reason is stored only in `audit_logs.metadata`** (0031:154-161). There is no column for it on the submission. `PAYMENT_REJECTED` is enqueued without the reason (notifications.py:68-79), and drain enrichment adds only `claimed_amount_cents` (api/cron/services/outbox_drain.py:78-83). **No member-facing path shows the reason**, yet the reject modal tells the officer "They will see the reason" (components/finance/ProofQueue.tsx:118). That promise is false (FACT).

## 3. Attachments: an upload already exists

**Endpoint (FACT).** `POST /api/treasury/payments/submissions/{id}/evidence` (payments.py:136-167). Only the submitting member may attach (403 otherwise). Tested in tests/treasury/test_v1_balance_submissions.py:181-228.

**Transport (FACT).** JSON `{content_type, data_base64}`, decoded with `b64decode(validate=True)` (payments.py:62-64, 152-155). The client converts with `toBase64` (lib/dues.ts:291-295).

**Storage (FACT).** Postgres `payment_evidence.data BYTEA` (0123:14-22) on the Supabase demo DB. There is no Supabase Storage, no bucket and no disk. Searches for storage, bucket and signed URLs in api/, migrations/ and config.py found nothing.

**How a read is authorized (FACT).** The file goes through the API: `GET /payments/evidence/{id}` returns JSON with `data_base64`. Only the owner or a holder of `treasury:payment:verify` may read it, scoped by chapter (payments.py:170-187; services/payments.py:289-309). The queue lists evidence metadata only, never the bytes (services/reports.py:95-106). The reviewer UI builds a `data:` URL and renders it in `<img>` (hooks/useFinance.ts:146-149; ProofQueue.tsx:141).

**Validation (FACT)**
- Size: 2 MiB, checked in the route (payments.py:158), the service (services/payments.py:93, 270-273) and a DB CHECK (0123:20).
- Not empty.
- That's all. **`content_type` is free text from the client** and is never checked or sniffed. A test stores `text/plain` (test_v1_balance_submissions.py:115-118).
- No filename is stored, so there is no path-traversal surface.
- **No check on submission status.** Evidence can be added after approval or rejection.
- **No limit on files per submission and no rate limit**, so a member can grow the database in 2 MiB steps. The size cap holds; the database growth is INFERENCE.

**Client side (FACT)**
- `accept="image/*"` (components/finance/InvoiceView.tsx:195-201).
- No client size check.
- An empty `File.type` falls back to `'image/png'` (useFinance.ts:99), so an unknown type gets mislabeled.
- When the upload fails (for example a 413), the toast says "Payment submitted, but the screenshot did not upload" (useFinance.ts:100-106). **The UI has no way to attach evidence afterwards.**

**HEIC (FACT).** There is no HEIC handling anywhere. INFERENCE: iOS Safari usually converts library photos to JPEG for `accept="image/*"`, but a HEIC that does get through will not render in Chrome or Firefox `<img>` for the reviewer.

**Image library (FACT).** None. requirements.txt has no Pillow. `fastapi[standard]` already includes python-multipart, and a multipart pattern with a bounded read exists in api/chapters/api/chapters.py:61-80 (roster CSV).

**Vercel (INFERENCE).** The JSON body is about 2.7 MB at the cap after base64, which is under Vercel's roughly 4.5 MB function request limit. Storing in the DB sidesteps Vercel's lack of a persistent disk.

**Dead related code (FACT).** `select_orphaned_proofs` (services/payments.py:324-349) is called only by a test. No cron job uses it.

## 4. Receipts and payment confirmation

**Treasury outbox events (FACT).** All are email (api/treasury/notifications.py). The default dedup key is `{EVENT}:{target_id}` (api/platform/outbox.py:99), and the insert is ON CONFLICT DO NOTHING (:41).

| Event | Trigger | Dedup key |
|---|---|---|
| INVOICE_ISSUED | `create_invoice[_v2]`, `issue_event_fines` (services/invoices.py:54, 99, 280). **Not bulk dues runs** (:238-259) | `INVOICE_ISSUED:{invoice_id}` |
| PAYMENT_APPROVED | first verify or record (services/payments.py:156) | `PAYMENT_APPROVED:{submission_id}` |
| PAYMENT_REJECTED | every reject call (:82). Dedup absorbs replays | `PAYMENT_REJECTED:{submission_id}` |
| REFUND_ISSUED | services/refunds.py:42 | `REFUND_ISSUED:{refund_id}` |
| PAYMENT_REMINDER | officer reminder (§5) | `PAYMENT_REMINDER:{member_id}:{YYYY-MM-DD}` (notifications.py:126) |

**A confirmation email on approval already exists (FACT).** It is `PAYMENT_APPROVED`, with subject "Payment recorded" and body "Payment recorded: $X. Thank you." (api/platform/message_templates.py:79-83, 273). The amount comes from drain enrichment. The cron drain runs every 5 minutes (vercel.json crons), and real sending needs `EMAIL_DELIVERY_MODE=smtp` plus the SMTP settings (api/config.py:41-49). The email does **not** include the receipt id, method, reference, which invoices were covered, or the remaining balance.

**Gap (FACT).** Bulk dues runs send no INVOICE_ISSUED email.

## 5. Reminders

**Backend already built (FACT).** `POST /api/memberadmin/remind/{member_id}`, gated by `standing:remind` (api/memberadmin/api/scores.py:28-108):
- Reads open invoices, then `remaining_by_invoice`.
- Enqueues nothing when nothing is owed, so the day's dedup key is not used up.
- Otherwise enqueues `PAYMENT_REMINDER` with count and total.
- Dedup is one per member per day. `queued:false` means a duplicate.
- Template: message_templates.py:100-119. It refuses to render a $0 reminder.
- Tests: tests/memberadmin/test_payment_reminder.py and tests/cron/test_drain_outbox.py:385-440.

**History (FACT).** The `message_outbox` rows are the history. Officers can see them through `GET /api/announcements/outbox`, but only with `announcements:send`, and treasury rows also need `treasury:audit:view` (api/announcements/api/announcements.py:95-107).

**Missing (FACT)**
- **No frontend button.** greekos/src never calls `/remind`.
- No bulk "remind everyone who owes".
- No schedule.
- The "day" is the server's local date (`date.today()`, notifications.py:117), which is UTC on Vercel, not the chapter's timezone. The UTC part is INFERENCE.
- The scores.py:38-41 docstring still mentions "direct verified payments", which is stale since 0165.

## 6. Financial invariants and audit (FACT)

- **Ledger and audit log are append-only.** Triggers block DELETE and allow only `active→invalidated` (0005:105-160). The same triggers protect `receipts` (0030:23-31), `payment_evidence` (0123:27-35) and `payment_allocations` (0124:41-49). Amount and owner columns are frozen (0168, 0208).
- **Chapter guards** live in the RPC bodies: `WHERE … chapter_id = p_chapter_id` and member/invoice ownership checks (0080; 0123:76; 0166:37-39; 0205:172). Routes take `chapter_id` from the session.
- **RLS** policies exist but the app connects as the owner, so they never apply at runtime (CLAUDE.md). The policies still use the old capability names `treasury:read` and `payment:review`, mapped in 0147:152.
- **Tests protecting these:** test_chunk0_foundations.py:149-309 (ledger and audit immutability, RPC rollback); test_chunkC_payments.py (receipt complete and immutable, double-verify concurrency, exactly one approval notification, reject has no money effect); test_chunkH_tenant_guards.py (cross-chapter); test_v1_balance_submissions.py (evidence cap, append-only, owner/reviewer authorization); test_record_payment.py (atomic, hash conflict, cross-chapter); test_single_coverage.py, test_v1_allocation.py, test_refund_reversal_order.py; test_chunkG_rebuild_hardening.py (drift, notify dedup).
- **Untested (FACT):** evidence content type, adding evidence after review, evidence count.

## 7. Frontend finance UI (FACT unless marked)

There is one `FinanceModule` for everyone (App.tsx:193). Tabs are gated with `can()`.
- **"My invoices"** shows open invoices only (from the dashboard). Its copy says "Everything the chapter has billed you" (components/FinanceModule.tsx:270), which is wrong once something is paid: paid invoices disappear. There is no paid/unpaid filter.
- **InvoiceView** shows amount, paid so far, awaiting verification, still owed, how to pay (a hard-coded constant in config/treasury.ts) and the proof form with the file input.
- **"Payments" tab** is built from the officer `/dashboard` `recent_payments` (useFinance.ts:153-158). **A member always sees it empty**, and the "Recent payments" KPI shows $0.00. Members have no payment history.
- **"Fines" tab** shows the member's own fines, including Paid and Waived.
- **"Balances" tab** shows standing-derived unpaid fines for every member. INFERENCE: a member session gets `[]` from the optional officer call, so every row reads $0.00.
- **Proof queue** (`treasury:payment:verify`): verify, reject with a reason, and view evidence as `<img>`.
- **Not present:** receipts UI, statement UI, reminder UI, re-attaching evidence, viewing rejected submissions.
- **Mobile:** `sm:` breakpoints, `min-h-11` tap targets, horizontally scrolling tabs and tables, columns hidden below `sm`. Usable.

## 8. Over-engineering and dead code (FACT)

- `services/payments.verify_payment` (v1 RPC), `services/invoices.create_invoice` (v1), `select_orphaned_proofs` and `_as_datetime` have test-only callers.
- `FineToInvoice` is an unused DTO, documented as such.
- Duplicate routes `/verify` and `/verify-v1`, `/reject` and `/reject-v1`. The URLs are frozen, so keep them.
- Backend-only surface with no UI: balance-submissions, reallocate, allocations, statement, receipts, member balance, report, rebuild. These are API, not necessarily dead.
- Small things: the evidence size check appears three times (route, service, DB); `_parse_ts` is duplicated (services/invoices.py:146, member_dashboard.py:16); the dashboard GET writes the balance cache (member_dashboard.py:32-33); there is no `api/treasury/auth.py`, and permission strings are repeated as literals across the route files.

---

## Recommendations (minimal)

### Terminology
The ledger records a **verified payment**. Each one gets exactly one immutable **receipt** (0030; 0166:62-65), with the same amount and no invoice link (allocations hold that). A **paid invoice** is only a status that can change back after a refund (0167). Use these terms:
- **"receipt"** for the per-payment record and its email ("Payment receipt").
- **"paid invoice"** only for invoice status in history lists.
- Avoid "payment confirmation" as a separate concept. It is the same thing as the existing `PAYMENT_APPROVED` email.

### (a) Image-only upload
Keep the current design: the existing endpoint, BYTEA storage and API-proxied reads with owner-or-verifier checks. That is the right choice on Vercel plus Supabase. Supabase Storage would add a service key, signed URLs and a second store for no gain at pilot scale.

New work, all in `add_submission_evidence`:
1. **Sniff magic bytes and ignore the client `content_type`.**
   - PNG: starts with `\x89PNG\r\n\x1a\n`.
   - JPEG: starts with `\xff\xd8\xff`.
   - HEIC: `data[4:8]==b'ftyp'` and `data[8:12]` in {`heic`,`heix`,`hevc`,`hevx`,`mif1`,`msf1`}.
   - Store the sniffed MIME type. Return 415 otherwise.
   - This is about 10 lines of stdlib, no Pillow. Pillow cannot read HEIC without pillow-heif anyway.
2. Allow evidence only while `submission.status == 'pending'`, and cap files per submission (for example 3).
3. Keep the 2 MiB cap.
4. Client: `accept="image/png,image/jpeg,image/heic"`, a size check before sending, and drop the `'image/png'` fallback. Optionally downscale to JPEG with canvas when over 2 MiB.
5. Reviewer: if the type is `image/heic`, show a download link instead of `<img>`.
6. Add a "Add screenshot" action on the member's pending submission.

Optional: switch to multipart using the roster pattern (chapters.py:61-80). It is not needed; base64 fits.

### (b) Paid invoice history
**Frontend-only for a first version.** `GET /members/{me}/statement` already returns paid invoices (raw status) and payments for the member themself. Add a "History" view and fix the "My invoices" copy and the member-empty "Payments" tab.

A small backend change is needed only to show method, reference or receipt id per payment: enrich `detail` in services/reports.py:180-189 from `payment_submissions` and `receipts`. Showing rejected submissions with their reason also needs the backend, because the reason sits only in `audit_logs`. Expose it through the dashboard or statement.

Officers already have `/members/{id}/statement` and `/payments/submissions?status=approved|rejected`.

### (c) Receipt email on approval
This already exists: `PAYMENT_APPROVED`, deduped on `PAYMENT_APPROVED:{submission_id}`, fired once on verify and on record. Do not add a new event type. Two small changes:
1. Pass `payload={receipt_id, method, proof_ref, allocated_cents, leftover_cents}` from `_after_verify_v2` (services/payments.py:149-163). `vp` already carries `allocated_cents` and `leftover_cents`; get `receipt_id` by `verified_payment_id`.
2. Extend `_payment_approved` and its subject to "Payment receipt".

Delivery needs `EMAIL_DELIVERY_MODE=smtp` and the Gmail app password, which is already a human task.

### (d) Manual reminders
The backend and dedup are already done: `/api/memberadmin/remind/{id}`, one per member per day, through outbox `dedup_key`. What remains is frontend:
- A "Remind" button per row in the Balances tab, gated by `standing:remind`.
- A toast based on `queued`: "Reminder queued" or "Already reminded today".

Optional: a "Remind all with a balance" action that loops on the client, or a small bulk endpoint using `enqueue_many` with the same key function. Optional: compute the day in the chapter's timezone. History is already visible to officers through the announcements outbox view.

### Also fix
- The false "They will see the reason" text (ProofQueue.tsx:118), or actually expose the reason (see (b)).
- Bulk dues runs send no INVOICE_ISSUED email.
