# 05 · Finance tab: every button saves to the server

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `05-finance-tab` · **Wave:** 1 · **Agent:** Claude Fable 5.1 (worktree agent) · **Branch:** `fix/audit-05-finance-tab`
**Findings:** F-014, F-061, the client half of F-070, the copy half of F-032/F-030
**Goal:** the Finance tab stops inventing data. Payment, fine, invoice and adjustment each call the server, wait for it, and then show what the server returned.
**Architecture:** `useFinance.ts` keeps owning the API calls. The four fake handlers become `async`, call `api.ts`, then refetch; the client-built ledger (`led_1000+` ids) and local balance arithmetic are deleted. Pure decisions (which endpoint a transaction maps to, what the confirmation says) live in `src/lib/transaction.ts` with tests, as the existing frontend rules require.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` card F-014 (and F-061, F-070); decisions D1, D3, D7, D11 in `00-README.md`; the server contract for recording a payment is in `00-README.md` "Contracts" (built by stream 03 in parallel; code against the contract, do not wait for it).

## Global constraints

- Allowed files: `greekos/src/hooks/useFinance.ts`, `greekos/src/components/FinanceModule.tsx`, `greekos/src/components/finance/**`, `greekos/src/lib/transaction.ts` + its test, `greekos/src/lib/dues.ts` + its test, `greekos/src/api.ts` (add calls and DTOs only; do not reorder or rename existing ones), `greekos/src/adapters.ts` + test (finance adapters only), `greekos/src/types.ts` (finance types only), `greekos/src/App.tsx` (the one `Fragment key` line for F-061 and prop wiring for FinanceModule).
- No backend file, no new npm dependency, no change to `Money`/`formatMoney`/`dollarsToCents` or the strict money regex (F-049 was refuted).
- Frontend rules from the 2026-09-07 slice still hold: logic in `src/lib/*.ts` with a sibling `*.test.ts` (`node:test`), components stay dumb, cents everywhere except inside form inputs, `formatMoney(cents)` for display.
- A success toast is shown only after the awaited call resolves. On failure, show the server's message and leave the form open with its values.
- Nothing may be rendered that the server did not return. If a panel has no server source, remove the panel and say so in the report.
- Checks before every commit: `npm test && npm run lint` in `greekos/`; `npm run build` before the last commit.

## Review focus

1. Double submit: a second click while the first request is in flight must not create a second transaction (disable the button, and send an `Idempotency-Key` generated when the form opens and regenerated whenever the form's values change).
2. An adjustment of $500 or more comes back `pending` (second sign-off). The UI must say it is waiting for approval, not that the balance changed.
3. A member without the permission never sees a control that will 403 (`can(permissions, key)`), and a 403 that still happens is shown, not swallowed.
4. `backendDown` must block these four actions with a visible message, never drop them silently.
5. After each write, every number on the tab comes from a refetch, never from local arithmetic.

---

### Task 1: map each transaction kind to its server call (pure, tested)

**Files:** `greekos/src/lib/transaction.ts`, `greekos/src/lib/transaction.test.ts`, `greekos/src/api.ts`

**Interfaces (produced, used by Task 2):**

```ts
export type TransactionDraft =
  | { kind: 'Payment'; memberId: string; amountCents: number; method: PaymentMethod; invoiceId?: string; reference?: string }
  | { kind: 'Fine'; memberId: string; amountCents: number; reason: string; eventId?: string }
  | { kind: 'Invoice'; memberId: string; amountCents: number; description: string }
  | { kind: 'Adjustment'; memberId: string; deltaCents: number; reason: string };

export type ServerCall =
  | { call: 'recordPayment'; body: { member_id: string; amount_cents: number; method: string; invoice_id: string | null; reference: string | null } }
  | { call: 'issueEventFine'; eventId: string; memberIds: string[] }
  | { call: 'createInvoice'; body: { member_id: string; source: 'fine' | 'manual'; amount_cents: number; description: string } }
  | { call: 'createAdjustment'; body: { member_id: string; kind: 'manual_correction'; delta_cents: number; reason: string } };

export function planTransaction(draft: TransactionDraft): ServerCall;
```

Mapping: Payment → `recordPayment`. Fine with `eventId` → `issueEventFine` (existing `POST /api/fines/issue`; the server sets the flat amount, so the form must show that amount read-only for event fines). Fine without `eventId` → `createInvoice` with `source: 'fine'` and the reason as description. Invoice → `createInvoice` with `source: 'manual'`. Adjustment → `createAdjustment` with the signed `deltaCents`.

- [ ] **Step 1: failing tests** in `transaction.test.ts`: one per mapping above (five cases), plus: zero or negative `amountCents` throws; empty reason/description throws for Fine, Invoice and Adjustment; `deltaCents === 0` throws.
- [ ] **Step 2: run `npm test`, expect FAIL.**
- [ ] **Step 3: implement `planTransaction`.** Add to `api.ts`: `recordPayment(body, idempotencyKey)` → `POST /api/treasury/payments/record`; `createInvoice(body, idempotencyKey)` → `POST /api/treasury/invoices`; `createAdjustment(body, idempotencyKey)` → `POST /api/treasury/adjustments`. Follow how `runDuesBulk` passes its `Idempotency-Key` header (around `api.ts:617-630`). `PaymentMethod` is the server's set: `venmo | zelle | cash | bank_transfer | check`.
- [ ] **Step 4: run, expect PASS; commit** — `feat(greekos): plan finance transactions as server calls`

### Task 2: the four handlers call the server

**Files:** `greekos/src/hooks/useFinance.ts:160-310`, `greekos/src/components/FinanceModule.tsx:155-215, 707-712`, `greekos/src/components/finance/**`

- [ ] **Step 1:** replace `handleRecordPayment`, `handleIssueFine`, `handlePostInvoice`, `handlePostLedgerCorrection` with one `submitTransaction(draft, idempotencyKey): Promise<void>` that calls `planTransaction`, awaits the matching `api.*` call, then refetches fines, the treasury dashboard, the member dashboard and the review queue (the refetch functions already exist in this hook and in `useAppData`; reuse them). `handleApproveFinePayment(fineId)` ("mark paid") becomes a `Payment` draft with `invoiceId = fineId`, the fine's remaining cents, and a method the officer picks.
- [ ] **Step 2:** delete `setMemberBalance`, the `led_` id generation, every `setLedger`/`setPayments`/`setFines` call that fabricates a row, and the `enqueueOutbox` calls in this hook (it is a no-op stub; the server sends notices). If the "ledger" panel in `FinanceModule` then has no server-backed rows, check for an existing read (`grep -n "ledger\|audit" src/api.ts`); use it if there is one, otherwise remove the panel.
- [ ] **Step 3:** `AddTransactionModal` and the Pay / correction modals: `onSubmit` awaits `submitTransaction`; while pending the confirm button is disabled and reads "Saving…"; on success close and toast (`Recorded $X payment from NAME.` etc., same wording as today); on error keep the modal open and show the message inline. Generate the idempotency key with `crypto.randomUUID()` when the modal opens and again whenever a field changes.
- [ ] **Step 4:** adjustment result: when the response `status` is `pending`, toast `Adjustment of $X needs a second sign-off before it applies.`
- [ ] **Step 5:** gate each kind on its permission with the existing `can()` helper: Payment `treasury:payment:verify`, Fine `treasury:fines:issue` (event) or `treasury:invoice:create` (free-form), Invoice `treasury:invoice:create`, Adjustment `treasury:adjustment:create`. Add the pure gate to an existing `*-access.ts` module with a test, following the neighbouring `*-access.test.ts` files.
- [ ] **Step 6: `npm test && npm run lint`; commit** — `fix(greekos): finance transactions save to the server`

### Task 3: F-070 (client) — the dues-run key follows the form

**Files:** `greekos/src/components/finance/DuesRunModal.tsx:27`

- [ ] `DuesRunModal` holds one key for the life of the modal. Regenerate it whenever amount, due date, description or the member selection changes (a `useEffect` on those values, or derive the key in the submit handler from a stable hash of the payload; pick whichever is smaller). Map a 409 from the server to: "This dues run was already submitted with different details. Review and submit again." Commit — `fix(greekos): new idempotency key when a dues run is edited`

### Task 4: copy that matches the new money rules

**Files:** `greekos/src/lib/dues.ts` + test, `greekos/src/components/finance/**`

- [ ] Pay-proof form: where the UI implies a payment lands on the chosen invoice, that is now true (decision D7); remove any "applied to your oldest invoice" wording if present and make the confirmation read `Pays INVOICE first; anything left over goes to your oldest unpaid invoice.` A refunded invoice now reopens (decision D3): make sure a `partially_paid`/`unpaid` invoice that was previously paid renders as payable. Add or adjust `dues.test.ts` cases for any helper you touch. Commit — `fix(greekos): finance copy matches allocation and refund rules`

### Task 5: F-061 — no forced remount

**Files:** `greekos/src/App.tsx:176`

- [ ] Remove the `Fragment key={currentMember?.id ?? currentMemberName}` wrapper around `FinanceModule`. Then make sure switching "view as" still resets what must reset: any `useState` inside `FinanceModule` seeded from the member (open modal, selected invoice) gets a `useEffect` reset on `currentMember?.id`. Commit — `fix(greekos): FinanceModule reacts to member changes without remounting`

### Task 6: browser check

- [ ] Follow README "Browser check" with an officer login. Do each of the four kinds once against the running backend, reload the page, and confirm each one is still there. Until stream 03 is merged `POST /payments/record` returns 404: confirm the UI shows that error and keeps the form open, and say in the report that the payment path awaits integration. Run `npm run build`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").
