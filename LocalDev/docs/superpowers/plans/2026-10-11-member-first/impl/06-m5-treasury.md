# M5 — Treasury: member history, upload UX, receipts, reminders

> Read `00-README.md` first. Test first. Stay in your lane. M0 already hardened the upload server-side.

**Goal:** members see paid invoices and payments; uploads are image-only with honest errors and a retry; the approval email is a real receipt that cannot be lost; dues runs notify; members see rejection reasons; officers can remind one or all (D14, D15).
**Spec:** `../01-phase-b-design.md` §8; `../audit/treasury.md` §1, §4–§5, Recommendations; `../audit/comms.md` §2 (treasury rows), §5, §6.
**Migrations:** 0222, 0223.
**Allowed files:** backend `migrations/0222_payment_rejection_reason.sql`, `migrations/0223_treasurer_remind.sql`, `api/treasury/**`, `api/memberadmin/api/scores.py`, `api/memberadmin/api/schemas.py`, `api/platform/message_templates.py` (treasury templates + subjects only), `api/cron/services/outbox_drain.py` (treasury `_ENRICHMENT` only), tests under `tests/treasury/`, `tests/memberadmin/`, `tests/cron/test_templates.py`; frontend `components/finance/**`, `components/FinanceModule.tsx` (may be split into `components/me/Money.tsx` + `components/cabin/Treasury.tsx`), `lib/dues.ts`, `lib/money-history.ts`, `hooks/useFinance.ts`, `api.ts`/`types.ts` (M5 block), `routes.tsx` (`/me/money`, `/cabin/treasury` lines).

## T1 — Backend: rejection reason, receipt payload in-tx, dues-run emails, bulk remind, treasurer key

- [ ] `migrations/0222_payment_rejection_reason.sql`: `ALTER TABLE payment_submissions ADD COLUMN IF NOT EXISTS rejection_reason TEXT;` and `CREATE OR REPLACE FUNCTION tr_reject_payment` (live body `0031:120`, verify) setting the column from `p_reason`. Failing test first: after `/reject-v1 {reason}` the submission row has `rejection_reason`; the member dashboard includes `rejected` submissions with the reason (today only `pending`: `member_dashboard.py:48-56`); `PAYMENT_REJECTED` template renders the reason (`test_templates.py`).
- [ ] Receipt (D15): failing tests in `tests/treasury/test_receipt_email.py`: after `verify-v1`, the outbox row payload has `receipt_id`, `method`, `allocated_cents`, `leftover_cents`, `remaining_balance_cents`; the rendered email subject is "Payment receipt" and the body names the invoices covered; if the enqueue fails the verification **rolls back** (monkeypatch `enqueue` to raise inside the transaction; assert no `verified_payments` row). Implement: in `services/payments.py` wrap `call_rpc("tr_verify_payment_v2", …, sb=tx)` + `notify_payment_approved(…, sb=tx)` in `get_db().transaction()`; same for `record_payment`. Keep the dedup key `PAYMENT_APPROVED:{submission_id}`. Template `_payment_approved` extended; `_ENRICHMENT` in the drain falls back to the payload fields.
- [ ] Dues run (D15): failing test: `bulk_create_invoices` enqueues one `INVOICE_ISSUED` per created invoice, deduped on `INVOICE_ISSUED:{invoice_id}`, and a replay enqueues nothing. Implement with `enqueue_many`-style loop after the RPC (payload per invoice differs, so per-row `enqueue`), inside the same transaction client.
- [ ] Bulk remind (D14): failing tests `tests/memberadmin/test_remind_all.py`: `POST /api/memberadmin/remind` (no id) with `standing:remind` enqueues one `PAYMENT_REMINDER` per member with remaining > 0, none for $0, reports `{queued, skipped_already_today, skipped_zero}`; `GET /api/memberadmin/remind/preview` returns the same list without enqueueing; the day key uses the chapter timezone (freeze a clock across UTC midnight). Implement in `api/memberadmin/api/scores.py` reusing `remaining_by_invoice` grouped by member and `enqueue_payment_reminder` with `today = chapter-local date`.
- [ ] `migrations/0223_treasurer_remind.sql`: `INSERT INTO role_permissions (role_key, permission_key) VALUES ('treasurer','standing:remind') ON CONFLICT DO NOTHING;` Test in `tests/rbac/`-style but under `tests/memberadmin/test_remind_all.py`: a treasurer-only member passes the gate.
- [ ] Member receipt read: failing test: `GET /api/treasury/payments/receipts/{id}` by the paying member → 200 (owner), by another member → 404. Loosen `payments.py:314-323` to owner-or-`treasury:audit:view`; expose `receipt_id` in the statement's payment `detail` (`services/reports.py:180-189`) plus `method` and `proof_ref`.
- [ ] Checkpoint: `python3 -m pytest tests/treasury tests/memberadmin tests/cron/test_templates.py -q`.

## T2 — Member money (`/me/money`)

- [ ] `components/me/Money.tsx`: tabs **Open** (today's "My invoices" with proof submission), **History** (from `/members/{me}/statement`: paid/partially paid invoices, payments with method + receipt link, adjustments, refunds; grouped by month; `lib/money-history.ts` pure grouping, tested), **Pending** (submissions pending + rejected with reason and "Add screenshot"). Receipt link opens `GET /payments/receipts/{id}` in a sheet. Fix copy "Everything the chapter has billed you" → accurate.
- [ ] Upload UX: `accept="image/png,image/jpeg,image/heic"`, client size check (>2 MiB → inline message before upload; optional canvas downscale to JPEG when the file is a PNG/JPEG over the cap — do it only if under ~40 lines), thumbnail preview, the 415/409/413 messages mapped to plain text, "Add screenshot" retry on a pending submission. Remove the `'image/png'` fallback (`useFinance.ts:99`).
- [ ] Remove member-visible fabricated data: Balances/Payments tabs are **not** shown to members (`FinanceModule.tsx` member branch); KPIs computed only from the member's own data.
- [ ] Tests: history grouping; Money renders rejection reason from fixture; upload validator in `lib/dues.ts` (size, type).
- [ ] Checkpoint: `npm test && npm run lint`.

## T3 — Cabin treasury (`/cabin/treasury`)

- [ ] `components/cabin/Treasury.tsx`: existing officer tabs (Dues run, Add transaction, Proof queue, Balances, Fines) moved as-is; Balances rows get **Remind** (`standing:remind`) with toast from `queued` ("Reminder queued" / "Already reminded today"); toolbar **Remind everyone who owes** → preview sheet listing recipients and totals → confirm → result counts. Proof queue: HEIC evidence shows a download link instead of `<img>`; the false "They will see the reason" text now true (keep).
- [ ] Tests: Remind present iff `standing:remind`; preview renders N rows from fixture.
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Definition of done

M5 acceptance row; no member-facing screen reads an officer-only endpoint; `grep -n "image/png'" greekos/src/hooks/useFinance.ts` empty; checksums updated.

## Risks

- Moving the enqueue inside the RPC transaction changes failure semantics: an SMTP-unrelated outbox insert failure now blocks verification. That is the chosen trade (D15). The drain still delivers later.
- `enqueue` outside a transaction swallows errors; inside it raises — the test must use the transaction client.
