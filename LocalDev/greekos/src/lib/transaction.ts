import { formatMoney } from '../formatters';

/** The four things a treasurer records. Same words as the backend ledger. */
export type TransactionKind = 'Payment' | 'Fine' | 'Invoice' | 'Adjustment';

/** What the Add-transaction form holds while the officer types. */
export interface TransactionForm {
  kind: TransactionKind;
  memberId: string;
  memberName: string;
  /** Raw input text. Dollars live here and nowhere else. */
  amountDollars: string;
  memo: string;
}

/** The backend's `method` pattern on payments. */
export type PaymentMethod = 'venmo' | 'zelle' | 'cash' | 'bank_transfer' | 'check';

/** What an event fine costs. The server sets it; the form only shows it.
 *  ponytail: mirrors FLAT_FINE_CENTS in api/treasury/core/fines.py — read it
 *  from GET /api/fines/missed/{event_id} the day it becomes chapter data. */
export const EVENT_FINE_CENTS = 2500;

/** A validated transaction, in cents, ready to become one server call. */
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

/** Which endpoint a transaction lands on, with its exact body. Throws on a
 *  draft the server would reject, so nothing half-valid is ever sent. */
export function planTransaction(draft: TransactionDraft): ServerCall {
  if (!draft.memberId) throw new Error('Pick a member');
  const positive = (cents: number) => {
    if (cents <= 0) throw new Error('Amount must be more than $0.00');
  };
  const words = (text: string, what: string) => {
    const t = text.trim();
    if (!t) throw new Error(`Add a ${what}`);
    return t;
  };
  switch (draft.kind) {
    case 'Payment':
      positive(draft.amountCents);
      return {
        call: 'recordPayment',
        body: {
          member_id: draft.memberId,
          amount_cents: draft.amountCents,
          method: draft.method,
          invoice_id: draft.invoiceId ?? null,
          reference: draft.reference ?? null
        }
      };
    case 'Fine':
      positive(draft.amountCents);
      if (draft.eventId) return { call: 'issueEventFine', eventId: draft.eventId, memberIds: [draft.memberId] };
      return {
        call: 'createInvoice',
        body: { member_id: draft.memberId, source: 'fine', amount_cents: draft.amountCents, description: words(draft.reason, 'reason') }
      };
    case 'Invoice':
      positive(draft.amountCents);
      return {
        call: 'createInvoice',
        body: { member_id: draft.memberId, source: 'manual', amount_cents: draft.amountCents, description: words(draft.description, 'description') }
      };
    case 'Adjustment':
      if (draft.deltaCents === 0) throw new Error('Adjustment cannot be $0.00');
      return {
        call: 'createAdjustment',
        body: { member_id: draft.memberId, kind: 'manual_correction', delta_cents: draft.deltaCents, reason: words(draft.reason, 'reason') }
      };
  }
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

export function previewTransaction(draft: TransactionForm, balanceBeforeCents: number): TransactionPreview {
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
