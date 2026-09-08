# Plan 04 — Treasury: Add transaction with preview → confirm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Read `00-README.md` first. Plan 01 must be on `feat/greekos-hci`.

**Goal:** A treasurer records a Payment, Fine, Invoice, or Adjustment from one form: pick member, kind, dollars, memo → preview sentence with the new balance → confirm. The member pay modal prefills from the real balance. Copy is honest demo copy.

**Architecture:** `src/lib/transaction.ts` owns dollars→cents parsing and the preview math (tested). `useFinance` gains an invoice poster and a general adjustment poster; all four kinds stay client-local (decision D2). The form is a new `components/finance/AddTransactionModal.tsx`; `FinanceModule` loses the Issue Fine modal and grows nothing.

**Tech Stack:** React 19, TypeScript, `node:test`.

**Spec:** handoff § "3. Treasury Add Transaction prototype"; README decisions D2, D5, D12.

## Global Constraints

- Dollars only inside the input; cents everywhere else; `formatMoney` for display.
- Kinds are exactly `Payment | Fine | Invoice | Adjustment`.
- No "Venmo Gateway", no `big_ledger`, no "immutable" claims for a client-local ledger. Demo copy says it resets on reload.
- No new deps, no backend changes.

---

### Task 1: Transaction math

**Files:**
- Create: `LocalDev/greekos/src/lib/transaction.ts`
- Create: `LocalDev/greekos/src/lib/transaction.test.ts`

**Interfaces:**

```ts
export type TransactionKind = 'Payment' | 'Fine' | 'Invoice' | 'Adjustment';
export interface TransactionDraft { kind: TransactionKind; memberId: string; memberName: string; amountDollars: string; memo: string; }
export interface TransactionPreview {
  valid: boolean; error?: string;
  amountCents: number;        // absolute, what the ledger row shows
  deltaCents: number;         // signed effect on the balance owed
  balanceBeforeCents: number; balanceAfterCents: number;
  sentence: string;           // "Credit $50.00 to Jake → new balance $100.00"
}
export function dollarsToCents(input: string): number | null;
export function previewTransaction(draft: TransactionDraft, balanceBeforeCents: number): TransactionPreview;
```

- [ ] **Step 1: Write the failing tests**

Create `LocalDev/greekos/src/lib/transaction.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dollarsToCents, previewTransaction, TransactionDraft } from './transaction';

test('dollarsToCents parses money without float drift', () => {
  assert.equal(dollarsToCents('12.34'), 1234);
  assert.equal(dollarsToCents('0.1'), 10);
  assert.equal(dollarsToCents('1.005'), null);   // more than 2 decimals
  assert.equal(dollarsToCents('$50'), 5000);
  assert.equal(dollarsToCents('1,250.50'), 125050);
  assert.equal(dollarsToCents('-25'), -2500);
  assert.equal(dollarsToCents(''), null);
  assert.equal(dollarsToCents('abc'), null);
});

const draft = (over: Partial<TransactionDraft>): TransactionDraft => ({
  kind: 'Payment', memberId: 'm1', memberName: 'Jake Martinez', amountDollars: '50', memo: '', ...over
});

test('payment credits the balance and cannot go below zero', () => {
  const p = previewTransaction(draft({ amountDollars: '50' }), 12500);
  assert.equal(p.valid, true);
  assert.equal(p.deltaCents, -5000);
  assert.equal(p.balanceAfterCents, 7500);
  assert.equal(p.sentence, 'Credit $50.00 to Jake Martinez → new balance $75.00');
  assert.equal(previewTransaction(draft({ amountDollars: '500' }), 12500).balanceAfterCents, 0);
});

test('fine and invoice charge the balance', () => {
  const f = previewTransaction(draft({ kind: 'Fine', amountDollars: '25' }), 0);
  assert.equal(f.deltaCents, 2500);
  assert.equal(f.sentence, 'Charge $25.00 fine to Jake Martinez → new balance $25.00');
  const i = previewTransaction(draft({ kind: 'Invoice', amountDollars: '150' }), 2500);
  assert.equal(i.sentence, 'Invoice $150.00 to Jake Martinez → new balance $175.00');
});

test('adjustment keeps the sign the treasurer typed', () => {
  const down = previewTransaction(draft({ kind: 'Adjustment', amountDollars: '-10' }), 2500);
  assert.equal(down.deltaCents, -1000);
  assert.equal(down.amountCents, 1000);
  assert.equal(down.sentence, 'Adjust Jake Martinez by -$10.00 → new balance $15.00');
  const up = previewTransaction(draft({ kind: 'Adjustment', amountDollars: '10' }), 2500);
  assert.equal(up.sentence, 'Adjust Jake Martinez by +$10.00 → new balance $35.00');
});

test('invalid amounts and non-positive charges are rejected with a reason', () => {
  assert.deepEqual(previewTransaction(draft({ amountDollars: 'x' }), 0).valid, false);
  assert.equal(previewTransaction(draft({ amountDollars: '0' }), 0).error, 'Amount must be more than $0.00');
  assert.equal(previewTransaction(draft({ kind: 'Fine', amountDollars: '-5' }), 0).error, 'Amount must be more than $0.00');
  assert.equal(previewTransaction(draft({ kind: 'Adjustment', amountDollars: '0' }), 0).error, 'Adjustment cannot be $0.00');
  assert.equal(previewTransaction(draft({ memberId: '' }), 0).error, 'Pick a member');
});
```

- [ ] **Step 2: Run to verify it fails** — `npm test` — Expected: FAIL, `Cannot find module './transaction'`.

- [ ] **Step 3: Implement**

Create `LocalDev/greekos/src/lib/transaction.ts`:

```ts
import { formatMoney } from '../formatters';

/** The four things a treasurer records. Same words as the backend ledger. */
export type TransactionKind = 'Payment' | 'Fine' | 'Invoice' | 'Adjustment';

export interface TransactionDraft {
  kind: TransactionKind;
  memberId: string;
  memberName: string;
  /** Raw input text. Dollars live here and nowhere else. */
  amountDollars: string;
  memo: string;
}

export interface TransactionPreview {
  valid: boolean;
  error?: string;
  /** Absolute cents, what the ledger row shows. */
  amountCents: number;
  /** Signed effect on the balance owed. */
  deltaCents: number;
  balanceBeforeCents: number;
  balanceAfterCents: number;
  sentence: string;
}

/** "$1,250.50" → 125050. Null for anything that is not money with ≤2 decimals.
 *  String math, so 0.1 stays 10 and never 9.999. */
export function dollarsToCents(input: string): number | null {
  const m = input.trim().replace(/[$,\s]/g, '').match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
  if (!m) return null;
  const [, sign, whole, frac = ''] = m;
  const cents = Number(whole) * 100 + Number(frac.padEnd(2, '0'));
  return sign ? -cents : cents;
}

const signed = (cents: number) => `${cents < 0 ? '-' : '+'}${formatMoney(Math.abs(cents))}`;

export function previewTransaction(draft: TransactionDraft, balanceBeforeCents: number): TransactionPreview {
  const fail = (error: string): TransactionPreview => ({
    valid: false, error, amountCents: 0, deltaCents: 0, balanceBeforeCents, balanceAfterCents: balanceBeforeCents, sentence: ''
  });
  if (!draft.memberId) return fail('Pick a member');
  const cents = dollarsToCents(draft.amountDollars);
  if (cents === null) return fail('Enter a dollar amount like 25 or 12.50');

  const name = draft.memberName;
  let deltaCents: number;
  let sentenceHead: string;
  switch (draft.kind) {
    case 'Payment':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = -cents;
      sentenceHead = `Credit ${formatMoney(cents)} to ${name}`;
      break;
    case 'Fine':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentenceHead = `Charge ${formatMoney(cents)} fine to ${name}`;
      break;
    case 'Invoice':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentenceHead = `Invoice ${formatMoney(cents)} to ${name}`;
      break;
    case 'Adjustment':
      if (cents === 0) return fail('Adjustment cannot be $0.00');
      deltaCents = cents;
      sentenceHead = `Adjust ${name} by ${signed(cents)}`;
      break;
  }
  const balanceAfterCents = Math.max(0, balanceBeforeCents + deltaCents);
  return {
    valid: true,
    amountCents: Math.abs(cents),
    deltaCents,
    balanceBeforeCents,
    balanceAfterCents,
    sentence: `${sentenceHead} → new balance ${formatMoney(balanceAfterCents)}`
  };
}
```

- [ ] **Step 4: Run to verify it passes** — `npm test` — Expected: `ℹ fail 0`.

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/lib/transaction.ts LocalDev/greekos/src/lib/transaction.test.ts
git commit -m "feat(greekos): transaction preview math"
```

---

### Task 2: Invoice and adjustment posters in useFinance

**Files:**
- Modify: `LocalDev/greekos/src/hooks/useFinance.ts`

**Interfaces:**
- `handlePostLedgerCorrection(corr: { memberId; amountCents: number /* signed */; description; correctsEntryId?: string })` — `correctsEntryId` becomes optional. Row `amountCents` is absolute; `balanceAfterCents` honors the sign.
- New `handlePostInvoice(inv: { memberId: string; memberName: string; amountCents: number; description: string })` — appends a `DUES_CHARGE` row and raises the member's balance.
- The hook returns `handlePostInvoice` in addition to the existing four handlers.

- [ ] **Step 1: Make `correctsEntryId` optional**

In the `handlePostLedgerCorrection` signature change `correctsEntryId: string` to `correctsEntryId?: string`. In the built `entry`, change `authorizedBy` to `` `${currentMemberName} (Adjustment)` ``. Everything else stays.

- [ ] **Step 2: Add `handlePostInvoice`** after `handleIssueFine`:

```ts
  // ponytail: client-local invoice for the design lab. The real path is
  // POST /api/treasury/invoices; wire it when the form shape has survived a browser test.
  const handlePostInvoice = (inv: { memberId: string; memberName: string; amountCents: number; description: string }) => {
    const ledgerId = 'led_' + (1000 + ledger.length);
    const newBalanceCents = balanceCentsOf(inv.memberId) + inv.amountCents;
    setLedger(prev => [{
      id: ledgerId,
      sequence: ledger.length + 1,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      memberId: inv.memberId,
      memberName: inv.memberName,
      type: 'DUES_CHARGE',
      amountCents: inv.amountCents,
      balanceAfterCents: newBalanceCents,
      description: inv.description || 'Invoice',
      authorizedBy: `${currentMemberName} (Officer)`
    }, ...prev]);
    setMemberBalance(inv.memberId, newBalanceCents);
    showToast(`Invoiced ${formatMoney(inv.amountCents)} to ${inv.memberName}.`);
  };
```

Add `handlePostInvoice,` to the returned object.

- [ ] **Step 3: Soften the three toasts** in this file so nothing claims immutability:
  - `Payment of ${…} recorded to immutable ledger.` → `Recorded ${…} payment from ${paymentData.memberName}.`
  - `Assessed ${…} fine to ${…}.` stays.
  - `Linked audit correction committed to ledger.` → `Adjustment recorded.`

- [ ] **Step 4: Lint** — `npm run lint` — Expected: clean (FinanceModule still compiles; `correctsEntryId` is now optional).

- [ ] **Step 5: Commit**

```bash
git add LocalDev/greekos/src/hooks/useFinance.ts
git commit -m "feat(greekos): client-local invoice and general adjustment posters"
```

---

### Task 3: AddTransactionModal

**Files:**
- Create: `LocalDev/greekos/src/components/finance/AddTransactionModal.tsx`

**Interfaces:**

```ts
interface AddTransactionModalProps {
  members: Member[];
  balanceCentsOf: (memberId: string) => number;
  onSubmit: (draft: TransactionDraft, preview: TransactionPreview) => void;
  onClose: () => void;
}
```

- [ ] **Step 1: Create the component**

```tsx
import React, { useId, useState } from 'react';
import { Receipt } from 'lucide-react';
import type { Member } from '../../types';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { TransactionDraft, TransactionKind, TransactionPreview, previewTransaction } from '../../lib/transaction';

const KINDS: { kind: TransactionKind; help: string }[] = [
  { kind: 'Payment', help: 'Money received from the member' },
  { kind: 'Fine', help: 'A charge for a rule violation' },
  { kind: 'Invoice', help: 'Dues or another bill' },
  { kind: 'Adjustment', help: 'A signed correction, e.g. -10 to forgive $10' }
];

interface AddTransactionModalProps {
  members: Member[];
  balanceCentsOf: (memberId: string) => number;
  onSubmit: (draft: TransactionDraft, preview: TransactionPreview) => void;
  onClose: () => void;
}

/** Two steps: fill the form, read the preview sentence, confirm. */
export default function AddTransactionModal({ members, balanceCentsOf, onSubmit, onClose }: AddTransactionModalProps) {
  const ids = { member: useId(), kind: useId(), amount: useId(), memo: useId() };
  const [draft, setDraft] = useState<TransactionDraft>({
    kind: 'Payment', memberId: members[0]?.id || '', memberName: members[0]?.name || '', amountDollars: '', memo: ''
  });
  const [confirming, setConfirming] = useState(false);

  const balanceBefore = balanceCentsOf(draft.memberId);
  const preview = previewTransaction(draft, balanceBefore);

  const pickMember = (memberId: string) => {
    const m = members.find(x => x.id === memberId);
    setDraft(d => ({
      ...d,
      memberId,
      memberName: m?.name || '',
      // A payment usually settles what is owed; prefill it, still editable.
      amountDollars: d.kind === 'Payment' && !d.amountDollars && m ? (balanceCentsOf(memberId) / 100).toFixed(2) : d.amountDollars
    }));
  };

  const pickKind = (kind: TransactionKind) =>
    setDraft(d => ({
      ...d,
      kind,
      amountDollars: kind === 'Payment' && !d.amountDollars ? (balanceBefore / 100).toFixed(2) : d.amountDollars
    }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!preview.valid) return;
    if (!confirming) { setConfirming(true); return; }
    onSubmit(draft, preview);
    onClose();
  };

  return (
    <Modal maxWidth="max-w-lg">
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
          <Receipt className="w-5 h-5 text-gold" />
          Add transaction
        </h3>
        <button type="button" onClick={onClose} aria-label="Close" className="text-slate-500 hover:text-slate-800 font-bold cursor-pointer">✕</button>
      </div>

      <p className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
        Demo: this is recorded in your browser only and resets on reload.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor={ids.member} className="text-xs font-semibold text-slate-700 block mb-1">Member</label>
          <select id={ids.member} value={draft.memberId} onChange={e => pickMember(e.target.value)} disabled={confirming}
            className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold bg-white">
            {members.map(m => <option key={m.id} value={m.id}>{m.name} · balance {formatMoney(balanceCentsOf(m.id))}</option>)}
          </select>
        </div>

        <fieldset disabled={confirming}>
          <legend className="text-xs font-semibold text-slate-700 mb-1">Kind</legend>
          <div className="grid grid-cols-2 gap-2">
            {KINDS.map(({ kind, help }) => (
              <label key={kind} className={`p-2.5 rounded-lg border text-xs cursor-pointer ${draft.kind === kind ? 'border-gold bg-amber-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                <input type="radio" name="kind" value={kind} checked={draft.kind === kind} onChange={() => pickKind(kind)} className="mr-1.5" />
                <span className="font-bold text-slate-900">{kind}</span>
                <span className="block text-slate-500 pl-5">{help}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor={ids.amount} className="text-xs font-semibold text-slate-700 block mb-1">Amount ($)</label>
            <input id={ids.amount} type="text" inputMode="decimal" value={draft.amountDollars} disabled={confirming}
              onChange={e => setDraft(d => ({ ...d, amountDollars: e.target.value }))}
              placeholder={draft.kind === 'Adjustment' ? '-10.00' : '25.00'}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 font-mono focus:outline-none focus:border-gold" required />
          </div>
          <div>
            <label htmlFor={ids.memo} className="text-xs font-semibold text-slate-700 block mb-1">Memo</label>
            <input id={ids.memo} type="text" value={draft.memo} disabled={confirming}
              onChange={e => setDraft(d => ({ ...d, memo: e.target.value }))}
              placeholder={draft.kind === 'Fine' ? 'Missed chapter (Bylaw II.C.4)' : 'Fall dues'}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold" />
          </div>
        </div>

        <div role="status" className={`p-3 rounded-lg text-xs font-semibold ${preview.valid ? 'bg-slate-50 text-slate-800 border border-slate-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {preview.valid ? preview.sentence : preview.error}
        </div>

        <div className="flex gap-2">
          {confirming && (
            <button type="button" onClick={() => setConfirming(false)} className="flex-1 min-h-11 border border-slate-200 text-slate-700 font-bold rounded-lg text-xs cursor-pointer hover:bg-slate-50">
              Back
            </button>
          )}
          <button type="submit" disabled={!preview.valid}
            className={`flex-1 min-h-11 font-bold rounded-lg text-xs cursor-pointer disabled:opacity-50 ${confirming ? 'bg-navy text-gold hover:bg-slate-800' : 'bg-gold text-navy hover:bg-[#c5a02b]'}`}>
            {confirming ? `Confirm ${draft.kind.toLowerCase()}` : 'Preview'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
```

- [ ] **Step 2: Lint** — `npm run lint` — Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add LocalDev/greekos/src/components/finance/AddTransactionModal.tsx
git commit -m "feat(greekos): add-transaction modal with preview and confirm"
```

---

### Task 4: Wire FinanceModule; honest copy; pay-modal prefill

**Files:**
- Modify: `LocalDev/greekos/src/components/FinanceModule.tsx`
- Modify: `LocalDev/greekos/src/App.tsx` (Finance props)

**Interfaces:**
- `FinanceModuleProps` gains `myBalance: MemberBalance | null; onPostInvoice: (inv: { memberId: string; memberName: string; amountCents: number; description: string }) => void;`
- `onPostLedgerCorrection`'s `correctsEntryId` becomes optional in the prop type.
- Removes: `showIssueFineModal`, `selectedMemberId`, `fineAmount`, `fineReason`, `handleIssueFineSubmit`, the Issue Fine modal.

- [ ] **Step 1: Props and imports**

Add imports:

```ts
import AddTransactionModal from './finance/AddTransactionModal';
import type { MemberBalance } from '../lib/balance';
import type { TransactionDraft, TransactionPreview } from '../lib/transaction';
```

Add to props (and destructure): `myBalance: MemberBalance | null;` and `onPostInvoice: (inv: { memberId: string; memberName: string; amountCents: number; description: string }) => void;`. Change `correctsEntryId: string` to `correctsEntryId?: string` in `onPostLedgerCorrection`.

- [ ] **Step 2: State swap**

Replace `const [showIssueFineModal, setShowIssueFineModal] = useState(false);` with `const [showAddTransaction, setShowAddTransaction] = useState(false);`.

Delete the "Issue Fine Form" state (three `useState` lines) and `handleIssueFineSubmit`.

Replace `const [payAmount, setPayAmount] = useState('150');` with `const [payAmount, setPayAmount] = useState('');`.

Add a helper after `currentMember`:

```ts
  const balanceCentsOf = (memberId: string) => {
    const m = safeMembers.find(x => x.id === memberId);
    return m ? (m.duesBalanceCents ?? Math.round((m.duesBalance || 0) * 100)) : 0;
  };

  /** One dispatcher for the four kinds; each lands on an existing handler. */
  const submitTransaction = (draft: TransactionDraft, preview: TransactionPreview) => {
    switch (draft.kind) {
      case 'Payment':
        onRecordPayment({
          memberId: draft.memberId, memberName: draft.memberName,
          amount: preview.amountCents / 100, amountCents: preview.amountCents,
          type: 'Dues', paymentMethod: 'Cash', reference: draft.memo || 'IN_PERSON'
        });
        break;
      case 'Fine':
        onIssueFine({
          memberId: draft.memberId, memberName: draft.memberName,
          amount: preview.amountCents / 100, amountCents: preview.amountCents,
          reason: draft.memo || 'Fine', issuedBy: currentMemberName
        });
        break;
      case 'Invoice':
        onPostInvoice({ memberId: draft.memberId, memberName: draft.memberName, amountCents: preview.amountCents, description: draft.memo });
        break;
      case 'Adjustment':
        onPostLedgerCorrection({ memberId: draft.memberId, amountCents: preview.deltaCents, description: draft.memo || 'Adjustment' });
        break;
    }
  };
```

- [ ] **Step 3: Header CTA**

Replace the officer `Issue Fine Citation` button with:

```tsx
          {isOfficer && (
            <button
              type="button"
              onClick={() => setShowAddTransaction(true)}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              Add transaction
            </button>
          )}
```

Change the member button label `Pay My Dues / Fines` → `Pay balance` and its `onClick` to:

```tsx
onClick={() => { setPayAmount(myBalance ? (myBalance.outstandingCents / 100).toFixed(2) : ''); setShowPayModal(true); }}
```

- [ ] **Step 4: Copy sweep in this file**

| Old | New |
|---|---|
| `Dues, payments, fines, and the chapter ledger.` | keep |
| `Total Chapter Receivables` / `Outstanding brother dues balances` | `Outstanding (demo ledger)` / `Unpaid fines plus demo transactions` |
| `Collected This Semester` | `Collected` |
| `Unpaid Fines Outstanding` / `active citations` | `Unpaid fines` / `unpaid` |
| tab `Member Balances & Dues` | `Balances` |
| tab `Append-Only Audit Ledger` | `Chapter ledger` |
| tab `Fines & Infractions (N)` | `Fines (N)` |
| tab `Payment Transactions (N)` | `Payments (N)` |
| `Active Brotherhood Receivables` / `Breakdown of member balances, payment standing, and semester dues status.` | `Balances` / `Starts from unpaid fines; demo transactions adjust it locally.` |
| column `Outstanding Balance` | `Balance` |
| `Immutable Chapter Financial Ledger (\`big_ledger\`)` | `Chapter ledger` |
| `Permanent, append-only record. Entries cannot be edited or deleted. Corrections are recorded as linked offsetting adjustment transactions.` | `Demo ledger: rows are recorded in this browser and reset on reload. Corrections are added as adjustment rows, never edits.` |
| `Disciplinary Fines & Violations` / `Issued for unexcused attendance or house rule infractions.` | `Fines` / `Issued for unexcused absences and rule violations.` |
| `Clear / Settle` | `Mark paid` |
| `Payment Gateway Records` / `Real-time incoming ACH, card, and Venmo dues settlement receipts.` | `Payments` / `Verified payments from the backend, plus demo payments recorded here.` |
| pay modal title `Settle Dues / Fines Balance` | `Pay balance` |
| `Current Outstanding Balance:` + `{formatMoney(currentMember.duesBalanceCents …)}` | `Balance owed` + `{formatMoney(myBalance?.outstandingCents ?? 0)}` |
| option `Venmo Gateway` / `Debit / Credit Card` / `ACH Bank Transfer` | `Venmo` / `Card` / `Bank transfer` |
| `Submit Payment Authorization` | `Record payment (demo)` |
| correction modal title `Post Linked Ledger Correction` | `Add adjustment` |
| `Adjustment Amount in Cents (e.g. -5000 for -$50.00)` | keep the cents input but label `Adjustment in cents (negative reduces the balance)` |
| `Commit Linked Audit Adjustment` | `Record adjustment` |

Add under the pay modal's form a demo note identical to the one in `AddTransactionModal`.

- [ ] **Step 5: Render the modal**

Delete the whole `{showIssueFineModal && ( <Modal> … </Modal> )}` block. In its place:

```tsx
      {showAddTransaction && (
        <AddTransactionModal
          members={safeMembers}
          balanceCentsOf={balanceCentsOf}
          onSubmit={submitTransaction}
          onClose={() => setShowAddTransaction(false)}
        />
      )}
```

Remove the now-unused `AlertCircle` import if tsc flags it (it is still used in the Fines tab header; leave it if so).

- [ ] **Step 6: App wiring**

In `App.tsx`, add to `<FinanceModule …>`:

```tsx
          myBalance={app.myBalance}
          onPostInvoice={finance.handlePostInvoice}
```

- [ ] **Step 7: Lint and test** — `npm run lint && npm test` — Expected: clean; `ℹ fail 0`.

- [ ] **Step 8: Browser check**

As Jake: Treasury → Add transaction. Pick a member, kind Payment: the amount prefills with that member's balance; the preview reads "Credit $X to Name → new balance $Y"; press Preview, then Confirm payment: the toast fires, the Balances row drops, the Chapter ledger tab shows a PAYMENT_CREDIT row. Repeat with Fine $25 (balance rises, Fines tab shows it), Invoice $150 (DUES_CHARGE row), Adjustment -10 (ADJUSTMENT_CORRECTION row, balance down $10). Amount "abc" shows the red error and disables Preview.

Switch to Member view: "Pay balance" opens the modal with the real balance owed and the amount prefilled from it, not $150.

- [ ] **Step 9: Commit**

```bash
git add LocalDev/greekos/src/components/FinanceModule.tsx LocalDev/greekos/src/App.tsx
git commit -m "feat(greekos): add-transaction CTA, honest treasury copy, pay modal prefill"
```

---

## Done when

- A treasurer records Payment, Fine, Invoice, Adjustment from one form with a confirm step.
- Pay modal prefills from the real balance owed.
- No `big_ledger`, "Venmo Gateway", "immutable", or "Issue Fine Citation" strings remain: `grep -rn "big_ledger\|Venmo Gateway\|immutable\|Issue Fine Citation" LocalDev/greekos/src` returns nothing.
- Four commits; tests and lint clean.
