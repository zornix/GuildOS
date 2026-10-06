/** The dues run → invoice → proof → verify loop, minus the rendering.
 *
 *  Every permission key here is the exact string the endpoint checks, so the
 *  control and the route it calls can never drift apart (#79).
 */

import type { OpenInvoiceDto, PaymentSubmissionDto } from '../api';
import { formatMoney } from '../formatters';
import { dollarsToCents, type TransactionKind } from './transaction';

/** POST /api/treasury/invoices and /invoices/bulk. */
export const INVOICE_CREATE_KEY = 'treasury:invoice:create';
/** POST /api/treasury/payments/record, …/submissions/{id}/verify-v1 | reject-v1,
 *  and GET /api/treasury/payments/submissions. Everyone holding it is the
 *  treasury board. */
export const PAYMENT_VERIFY_KEY = 'treasury:payment:verify';
/** POST /api/fines/issue. */
export const FINES_ISSUE_KEY = 'treasury:fines:issue';
/** POST /api/treasury/adjustments — the ledger correction rows. */
export const ADJUSTMENT_CREATE_KEY = 'treasury:adjustment:create';

/** Which Add-transaction kinds a session may record, each by the key its
 *  endpoint checks. A fine is two endpoints: on an event (FINES_ISSUE_KEY)
 *  or free-form as a fine invoice (INVOICE_CREATE_KEY). */
export interface TransactionAccess {
  kinds: TransactionKind[];
  eventFines: boolean;
  freeFormFines: boolean;
}

export function transactionAccess(permissions: Iterable<string>): TransactionAccess {
  const keys = new Set(permissions);
  const eventFines = keys.has(FINES_ISSUE_KEY);
  const freeFormFines = keys.has(INVOICE_CREATE_KEY);
  const kinds: TransactionKind[] = [];
  if (keys.has(PAYMENT_VERIFY_KEY)) kinds.push('Payment');
  if (eventFines || freeFormFines) kinds.push('Fine');
  if (freeFormFines) kinds.push('Invoice');
  if (keys.has(ADJUSTMENT_CREATE_KEY)) kinds.push('Adjustment');
  return { kinds, eventFines, freeFormFines };
}

/** The methods the backend's `method` pattern accepts, with member-facing labels. */
export const PAYMENT_METHODS = [
  { value: 'venmo', label: 'Venmo' },
  { value: 'zelle', label: 'Zelle' },
  { value: 'cash', label: 'Cash' },
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'check', label: 'Check' }
] as const;

export type InvoiceStatus = 'Paid' | 'Overdue' | 'Partly paid' | 'Open' | 'Void';

export interface Invoice {
  id: string;
  /** What it is for, in the member's words. */
  description: string;
  /** dues | fine | manual | … — the V1 `source` vocabulary. */
  source: string;
  amountCents: number;
  remainingCents: number;
  paidCents: number;
  /** ISO timestamp, or '' when the invoice carries no due date. */
  dueAt: string;
  overdue: boolean;
  status: InvoiceStatus;
}

const SOURCE_LABELS: Record<string, string> = {
  dues: 'Chapter dues',
  fine: 'Fine',
  rent: 'Rent',
  utilities: 'Utilities',
  assessment: 'Assessment',
  manual: 'Charge'
};

/** A title for an invoice that has no description — a fine from the events
 *  path arrives without one. */
export function invoiceTitle(invoice: Invoice): string {
  return invoice.description || SOURCE_LABELS[invoice.source] || 'Charge';
}

/** The one place an invoice's headline status is decided.
 *  Nothing remaining wins over overdue: a paid-late invoice reads "Paid". */
export function invoiceStatus(dto: OpenInvoiceDto): InvoiceStatus {
  if (dto.status === 'void') return 'Void';
  if (dto.remaining_cents <= 0) return 'Paid';
  if (dto.overdue) return 'Overdue';
  return dto.remaining_cents < dto.amount_cents ? 'Partly paid' : 'Open';
}

export function adaptInvoice(dto: OpenInvoiceDto): Invoice {
  const remainingCents = Math.max(0, dto.remaining_cents);
  return {
    id: dto.id,
    description: dto.description || '',
    source: dto.source || 'manual',
    amountCents: dto.amount_cents,
    remainingCents,
    paidCents: Math.max(0, dto.amount_cents - remainingCents),
    dueAt: dto.due_at || '',
    overdue: dto.overdue,
    status: invoiceStatus(dto)
  };
}

export const adaptInvoices = (rows: OpenInvoiceDto[] | undefined): Invoice[] =>
  (rows || []).map(adaptInvoice);

/** "2026-10-01T00:00:00+00:00" → "Oct 1, 2026". Empty for no due date. */
export function formatDueDate(dueAt: string): string {
  if (!dueAt) return '';
  const d = new Date(dueAt);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── The dues run form ────────────────────────────────────────────────────────

export interface DuesRunDraft {
  title: string;
  amountDollars: string;
  /** YYYY-MM-DD from <input type="date">; optional. */
  dueDate: string;
  /** Members the run charges. */
  recipientIds: string[];
}

export interface DuesRunItem {
  member_id: string;
  kind: 'dues';
  amount_cents: number;
  description: string;
  due_at?: string;
}

export interface DuesRunPlan {
  valid: boolean;
  error?: string;
  items: DuesRunItem[];
  amountCents: number;
  totalCents: number;
  /** What the officer confirms before the batch is sent. */
  sentence: string;
}

/** Validate the form and build the exact bulk payload, or say what is missing.
 *  A due date is sent as end-of-day local time, so "due Oct 1" is not overdue
 *  at 00:01 on Oct 1. */
export function planDuesRun(draft: DuesRunDraft): DuesRunPlan {
  const fail = (error: string): DuesRunPlan => ({
    valid: false, error, items: [], amountCents: 0, totalCents: 0, sentence: ''
  });

  const title = draft.title.trim();
  if (!title) return fail('Name the run, e.g. "Fall 2026 dues"');

  const amountCents = dollarsToCents(draft.amountDollars);
  if (amountCents === null) return fail('Enter a dollar amount like 250 or 250.50');
  if (amountCents <= 0) return fail('Amount must be more than $0.00');

  if (draft.recipientIds.length === 0) return fail('No recipients left — everyone is excluded');

  let dueAt: string | undefined;
  if (draft.dueDate) {
    const parsed = new Date(`${draft.dueDate}T23:59:59`);
    if (Number.isNaN(parsed.getTime())) return fail('Due date is not a real date');
    dueAt = parsed.toISOString();
  }

  const items = draft.recipientIds.map<DuesRunItem>(member_id => ({
    member_id,
    kind: 'dues',
    amount_cents: amountCents,
    description: title,
    ...(dueAt ? { due_at: dueAt } : {})
  }));

  const totalCents = amountCents * items.length;
  const due = draft.dueDate ? `, due ${formatDueDate(dueAt as string)}` : '';
  return {
    valid: true,
    items,
    amountCents,
    totalCents,
    sentence: `Invoice ${formatMoney(amountCents)} to ${items.length} member${
      items.length === 1 ? '' : 's'
    }${due} — ${formatMoney(totalCents)} billed.`
  };
}

// ── The "I paid" form ────────────────────────────────────────────────────────

export interface ProofDraft {
  amountDollars: string;
  method: string;
  note: string;
}

export interface ProofPlan {
  valid: boolean;
  error?: string;
  body: { invoice_id: string; claimed_amount_cents: number; method: string; proof_ref?: string };
}

const METHOD_VALUES = new Set<string>(PAYMENT_METHODS.map(m => m.value));

/** Validate a proof submission against the invoice it is paying.
 *  Overpaying is allowed — verification allocates the surplus to the member's
 *  other open invoices and leaves any leftover as credit. */
export function planProof(invoice: Invoice, draft: ProofDraft): ProofPlan {
  const fail = (error: string): ProofPlan => ({
    valid: false, error, body: { invoice_id: invoice.id, claimed_amount_cents: 0, method: '' }
  });

  const cents = dollarsToCents(draft.amountDollars);
  if (cents === null) return fail('Enter a dollar amount like 250 or 250.50');
  if (cents <= 0) return fail('Amount must be more than $0.00');
  if (!METHOD_VALUES.has(draft.method)) return fail('Pick how you paid');

  const note = draft.note.trim();
  return {
    valid: true,
    body: {
      invoice_id: invoice.id,
      claimed_amount_cents: cents,
      method: draft.method,
      ...(note ? { proof_ref: note } : {})
    }
  };
}

// ── The review queue ─────────────────────────────────────────────────────────

export interface ProofSubmission {
  id: string;
  memberId: string;
  memberName: string;
  invoiceId: string;
  claimedCents: number;
  method: string;
  note: string;
  submittedAt: string;
  evidenceIds: string[];
}

export function adaptSubmissions(
  rows: PaymentSubmissionDto[],
  memberNames: Map<string, string>
): ProofSubmission[] {
  return rows.map(row => ({
    id: row.id,
    memberId: row.member_id,
    memberName: memberNames.get(row.member_id) || 'Unknown member',
    invoiceId: row.invoice_id || '',
    claimedCents: row.claimed_amount_cents,
    method: PAYMENT_METHODS.find(m => m.value === row.method)?.label || row.method,
    note: row.proof_ref || '',
    submittedAt: row.created_at,
    evidenceIds: (row.evidence || []).map(e => e.id)
  }));
}

/** Rejecting is a decision a member reads, so the reason is mandatory —
 *  the endpoint 422s on an empty one. */
export const rejectionReasonValid = (reason: string): boolean => reason.trim().length > 0;

/** A File's bytes as bare base64, ready for the evidence endpoint. */
export function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
