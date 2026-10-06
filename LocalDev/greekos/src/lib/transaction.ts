import type { ChapterEvent, Member } from '../types';
import type { api as Api, IssueFinesResultDto } from '../api';
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
  /** Reference, reason or description — whichever the kind sends. */
  memo: string;
  method: PaymentMethod;
  /** Fine only: the required event it is for; empty for a free-form fine. */
  eventId?: string;
  /** Payment only: the invoice it should cover first (D7). */
  invoiceId?: string;
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
  /** Absolute cents, what the server row will show. */
  amountCents: number;
  /** Signed effect on what the member owes. */
  deltaCents: number;
  /** What the officer confirms. Never a projected balance: the server
   *  allocates payments and may hold a large adjustment for sign-off. */
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

export function previewTransaction(form: TransactionForm): TransactionPreview {
  const fail = (error: string): TransactionPreview => ({ valid: false, error, amountCents: 0, deltaCents: 0, sentence: '' });
  if (!form.memberId) return fail('Pick a member');
  const cents = dollarsToCents(form.amountDollars);
  if (cents === null) return fail('Enter a dollar amount like 25 or 12.50');

  const name = form.memberName;
  let deltaCents: number;
  let sentence: string;
  switch (form.kind) {
    case 'Payment':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = -cents;
      sentence = `Credit ${formatMoney(cents)} to ${name} — ${
        form.invoiceId
          ? 'pays this invoice first; anything left goes to their oldest open invoice.'
          : 'pays their oldest open invoice first.'
      }`;
      break;
    case 'Fine':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentence = `Charge ${formatMoney(cents)} fine to ${name}.`;
      break;
    case 'Invoice':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentence = `Invoice ${formatMoney(cents)} to ${name}.`;
      break;
    case 'Adjustment':
      if (cents === 0) return fail('Adjustment cannot be $0.00');
      deltaCents = cents;
      sentence = `Adjust ${name} by ${signed(cents)}.`;
      break;
  }
  return { valid: true, amountCents: Math.abs(cents), deltaCents, sentence };
}

/** The form as the cents draft `planTransaction` takes. Throws when the
 *  amount is not money; `planTransaction` checks everything else. */
export function draftFromForm(form: TransactionForm): TransactionDraft {
  const memo = form.memo.trim();
  const cents = dollarsToCents(form.amountDollars);
  if (cents === null) throw new Error('Enter a dollar amount like 25 or 12.50');
  switch (form.kind) {
    case 'Payment':
      return {
        kind: 'Payment', memberId: form.memberId, amountCents: cents, method: form.method,
        ...(form.invoiceId ? { invoiceId: form.invoiceId } : {}),
        ...(memo ? { reference: memo } : {})
      };
    case 'Fine':
      return form.eventId
        ? { kind: 'Fine', memberId: form.memberId, amountCents: EVENT_FINE_CENTS, reason: memo, eventId: form.eventId }
        : { kind: 'Fine', memberId: form.memberId, amountCents: cents, reason: memo };
    case 'Invoice':
      return { kind: 'Invoice', memberId: form.memberId, amountCents: cents, description: memo };
    case 'Adjustment':
      return { kind: 'Adjustment', memberId: form.memberId, deltaCents: cents, reason: memo };
  }
}

/** The events a fine can attach to: required, and already happened. */
export const finableEvents = (events: ChapterEvent[], today: string): ChapterEvent[] =>
  events.filter(e => e.required && e.date <= today);

export interface TransactionDeps {
  api: Pick<typeof Api, 'recordPayment' | 'issueFines' | 'createInvoice' | 'createAdjustment'>;
  members: Pick<Member, 'id' | 'name'>[];
  /** The last load failed; a write now would only fail later, so refuse it. */
  backendDown: boolean;
  /** Re-reads every number on the tab after a write. */
  refetch: () => Promise<unknown>;
  showToast: (message: string) => void;
}

/** The four officer transactions (D1). Resolves after the server has the row
 *  and the tab has been re-read; rejects with the message to show inline. */
export async function submitTransaction(deps: TransactionDeps, draft: TransactionDraft, idempotencyKey: string): Promise<void> {
  const { api } = deps;
  if (deps.backendDown) throw new Error('Not saved: the server is unreachable.');
  const call = planTransaction(draft);
  const name = deps.members.find(m => m.id === draft.memberId)?.name || 'the member';
  let message: string;
  switch (call.call) {
    case 'recordPayment':
      await api.recordPayment(call.body, idempotencyKey);
      message = `Recorded ${formatMoney(call.body.amount_cents)} payment from ${name}.`;
      break;
    case 'issueEventFine': {
      const result = await api.issueFines(call.eventId, call.memberIds) as IssueFinesResultDto;
      if (!result.issued_member_ids.includes(draft.memberId)) {
        throw new Error(`No fine for ${name}: they were present, excused, or already fined for that event.`);
      }
      message = `Assessed ${formatMoney(result.flat_fine_cents)} fine to ${name}.`;
      break;
    }
    case 'createInvoice':
      await api.createInvoice(call.body, idempotencyKey);
      message = call.body.source === 'fine'
        ? `Assessed ${formatMoney(call.body.amount_cents)} fine to ${name}.`
        : `Invoiced ${formatMoney(call.body.amount_cents)} to ${name}.`;
      break;
    case 'createAdjustment': {
      const adjustment = await api.createAdjustment(call.body, idempotencyKey);
      message = adjustment.status === 'pending'
        ? `Adjustment of ${formatMoney(Math.abs(adjustment.delta_cents))} needs a second sign-off before it applies.`
        : 'Adjustment recorded.';
      break;
    }
  }
  await deps.refetch();
  deps.showToast(message);
}
