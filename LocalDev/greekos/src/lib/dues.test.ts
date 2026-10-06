import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { OpenInvoiceDto } from '../api';
import { can } from './session';
import {
  ADJUSTMENT_CREATE_KEY,
  FINES_ISSUE_KEY,
  INVOICE_CREATE_KEY,
  PAYMENT_VERIFY_KEY,
  adaptInvoice,
  adaptSubmissions,
  duesRunErrorMessage,
  invoiceStatus,
  invoiceTitle,
  planDuesRun,
  planProof,
  rejectionReasonValid,
  transactionAccess
} from './dues';

const invoiceDto = (over: Partial<OpenInvoiceDto> = {}): OpenInvoiceDto => ({
  id: 'inv1',
  description: 'Fall 2026 dues',
  amount_cents: 25000,
  remaining_cents: 25000,
  due_at: '2026-10-01T23:59:59.000Z',
  overdue: false,
  source: 'dues',
  status: 'open',
  ...over
});

// ── invoice status + balance derivation ──────────────────────────────────────

test('an untouched invoice is Open, a partly covered one says so', () => {
  assert.equal(invoiceStatus(invoiceDto()), 'Open');
  assert.equal(invoiceStatus(invoiceDto({ remaining_cents: 10000 })), 'Partly paid');
});

test('nothing remaining reads Paid even when the due date has passed', () => {
  assert.equal(invoiceStatus(invoiceDto({ remaining_cents: 0, overdue: true })), 'Paid');
  assert.equal(invoiceStatus(invoiceDto({ remaining_cents: -500 })), 'Paid');
});

test('still owing past the due date is Overdue; a void invoice stays Void', () => {
  assert.equal(invoiceStatus(invoiceDto({ overdue: true })), 'Overdue');
  assert.equal(invoiceStatus(invoiceDto({ overdue: true, remaining_cents: 100 })), 'Overdue');
  assert.equal(invoiceStatus(invoiceDto({ status: 'void', remaining_cents: 25000 })), 'Void');
});

test('paid-so-far is the amount minus what is left, never negative', () => {
  assert.equal(adaptInvoice(invoiceDto({ remaining_cents: 10000 })).paidCents, 15000);
  const overpaid = adaptInvoice(invoiceDto({ remaining_cents: -1000 }));
  assert.equal(overpaid.remainingCents, 0);
  assert.equal(overpaid.paidCents, 25000);
});

test('an invoice with no description falls back to what it is for', () => {
  assert.equal(invoiceTitle(adaptInvoice(invoiceDto())), 'Fall 2026 dues');
  assert.equal(
    invoiceTitle(adaptInvoice(invoiceDto({ description: null, source: 'fine' }))),
    'Fine'
  );
  assert.equal(
    invoiceTitle(adaptInvoice(invoiceDto({ description: null, source: null }))),
    'Charge'
  );
});

// ── dues run form ────────────────────────────────────────────────────────────

const draft = (over = {}) => ({
  title: 'Fall 2026 dues',
  amountDollars: '250',
  dueDate: '2026-10-01',
  recipientIds: ['a', 'b', 'c'],
  ...over
});

test('a valid run becomes one bulk item per recipient', () => {
  const plan = planDuesRun(draft());
  assert.equal(plan.valid, true);
  assert.equal(plan.items.length, 3);
  assert.equal(plan.amountCents, 25000);
  assert.equal(plan.totalCents, 75000);
  assert.deepEqual(plan.items[0], {
    member_id: 'a',
    kind: 'dues',
    amount_cents: 25000,
    description: 'Fall 2026 dues',
    due_at: new Date('2026-10-01T23:59:59').toISOString()
  });
  assert.match(plan.sentence, /\$250\.00 to 3 members/);
  assert.match(plan.sentence, /\$750\.00 billed/);
});

test('the due date is end of day, so an invoice due today is not overdue today', () => {
  const due = new Date(planDuesRun(draft()).items[0].due_at as string);
  assert.equal(due.getHours(), 23);
  assert.equal(due.getDate(), 1);
});

test('a run with no due date omits due_at rather than sending null', () => {
  const plan = planDuesRun(draft({ dueDate: '' }));
  assert.equal(plan.valid, true);
  assert.equal('due_at' in plan.items[0], false);
});

test('a run needs a name, a positive amount and someone to bill', () => {
  assert.equal(planDuesRun(draft({ title: '  ' })).error, 'Name the run, e.g. "Fall 2026 dues"');
  assert.equal(planDuesRun(draft({ amountDollars: 'lots' })).valid, false);
  assert.equal(planDuesRun(draft({ amountDollars: '0' })).error, 'Amount must be more than $0.00');
  assert.equal(planDuesRun(draft({ amountDollars: '-5' })).error, 'Amount must be more than $0.00');
  assert.equal(
    planDuesRun(draft({ recipientIds: [] })).error,
    'No recipients left — everyone is excluded'
  );
});

test('an invalid run never produces items to send', () => {
  for (const bad of [{ title: '' }, { amountDollars: '' }, { recipientIds: [] }]) {
    assert.deepEqual(planDuesRun(draft(bad)).items, []);
  }
});

// ── proof form ───────────────────────────────────────────────────────────────

const invoice = adaptInvoice(invoiceDto());

test('a proof submission carries cents, the method key and the note', () => {
  const plan = planProof(invoice, { amountDollars: '125.50', method: 'venmo', note: ' @jake ' });
  assert.equal(plan.valid, true);
  assert.deepEqual(plan.body, {
    invoice_id: 'inv1',
    claimed_amount_cents: 12550,
    method: 'venmo',
    proof_ref: '@jake'
  });
});

test('an empty note is omitted, not sent blank', () => {
  const plan = planProof(invoice, { amountDollars: '10', method: 'cash', note: '   ' });
  assert.equal('proof_ref' in plan.body, false);
});

test('proof needs real money and a method the backend accepts', () => {
  assert.equal(planProof(invoice, { amountDollars: '', method: 'venmo', note: '' }).valid, false);
  assert.equal(
    planProof(invoice, { amountDollars: '0', method: 'venmo', note: '' }).error,
    'Amount must be more than $0.00'
  );
  assert.equal(
    planProof(invoice, { amountDollars: '25', method: 'crypto', note: '' }).error,
    'Pick how you paid'
  );
  assert.equal(planProof(invoice, { amountDollars: '25', method: '', note: '' }).valid, false);
});

test('paying more than the invoice is allowed — verification allocates the rest', () => {
  const plan = planProof(invoice, { amountDollars: '500', method: 'zelle', note: '' });
  assert.equal(plan.valid, true);
  assert.equal(plan.body.claimed_amount_cents, 50000);
});

test('a rejection must carry a reason', () => {
  assert.equal(rejectionReasonValid(''), false);
  assert.equal(rejectionReasonValid('   '), false);
  assert.equal(rejectionReasonValid('No screenshot attached'), true);
});

// ── review queue ─────────────────────────────────────────────────────────────

test('queue rows carry the member name, a readable method and the evidence ids', () => {
  const [row] = adaptSubmissions(
    [{
      id: 's1', member_id: 'm1', invoice_id: 'inv1', claimed_amount_cents: 25000,
      method: 'bank_transfer', status: 'pending', proof_ref: 'ref 991',
      created_at: '2026-09-15T10:00:00Z',
      evidence: [{ id: 'e1', content_type: 'image/png', size_bytes: 42 }]
    }],
    new Map([['m1', 'Jake Reed']])
  );
  assert.equal(row.memberName, 'Jake Reed');
  assert.equal(row.method, 'Bank transfer');
  assert.deepEqual(row.evidenceIds, ['e1']);
});

test('a submission with no evidence and an unknown member still renders', () => {
  const [row] = adaptSubmissions(
    [{
      id: 's2', member_id: 'ghost', invoice_id: null, claimed_amount_cents: 100,
      method: 'cash', status: 'pending', proof_ref: null, created_at: '2026-09-15T10:00:00Z'
    }],
    new Map()
  );
  assert.equal(row.memberName, 'Unknown member');
  assert.deepEqual(row.evidenceIds, []);
  assert.equal(row.invoiceId, '');
});

// ── gating follows the key the endpoint checks (#79) ─────────────────────────

test('the dues-run and verify controls gate on the endpoints own keys', () => {
  assert.equal(INVOICE_CREATE_KEY, 'treasury:invoice:create');
  assert.equal(PAYMENT_VERIFY_KEY, 'treasury:payment:verify');

  const treasurer = new Set([INVOICE_CREATE_KEY, PAYMENT_VERIFY_KEY]);
  assert.equal(can(treasurer, INVOICE_CREATE_KEY), true);
  assert.equal(can(treasurer, PAYMENT_VERIFY_KEY), true);

  // An officer-shaped session without the treasury keys gets neither control.
  const socialChair = new Set(['standing:view_all', 'events:create']);
  assert.equal(can(socialChair, INVOICE_CREATE_KEY), false);
  assert.equal(can(socialChair, PAYMENT_VERIFY_KEY), false);

  // Holding one key never implies the other.
  assert.equal(can(new Set([PAYMENT_VERIFY_KEY]), INVOICE_CREATE_KEY), false);
  assert.equal(can(new Set([INVOICE_CREATE_KEY]), PAYMENT_VERIFY_KEY), false);
});

test('each transaction kind is offered only to a holder of the key its endpoint checks', () => {
  assert.deepEqual(transactionAccess([]), { kinds: [], eventFines: false, freeFormFines: false });
  assert.deepEqual(transactionAccess([PAYMENT_VERIFY_KEY]).kinds, ['Payment']);
  assert.deepEqual(transactionAccess([FINES_ISSUE_KEY]), { kinds: ['Fine'], eventFines: true, freeFormFines: false });
  assert.deepEqual(transactionAccess([INVOICE_CREATE_KEY]), { kinds: ['Fine', 'Invoice'], eventFines: false, freeFormFines: true });
  assert.deepEqual(transactionAccess([ADJUSTMENT_CREATE_KEY]).kinds, ['Adjustment']);
  assert.deepEqual(
    transactionAccess([PAYMENT_VERIFY_KEY, FINES_ISSUE_KEY, INVOICE_CREATE_KEY, ADJUSTMENT_CREATE_KEY]).kinds,
    ['Payment', 'Fine', 'Invoice', 'Adjustment']
  );
  // An officer-shaped session without treasury keys records nothing.
  assert.deepEqual(transactionAccess(['standing:view_all', 'events:create']).kinds, []);
});

test('a dues run the server already holds under different details asks for a fresh look (F-070)', () => {
  assert.equal(
    duesRunErrorMessage({ status: 409 }),
    'This dues run was already submitted with different details. Review and submit again.'
  );
  const generic = 'Could not create the dues run. Try again — a retry will not bill anyone twice.';
  assert.equal(duesRunErrorMessage({ status: 500 }), generic);
  assert.equal(duesRunErrorMessage(new Error('boom')), generic);
});
