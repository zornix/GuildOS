import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  dollarsToCents,
  planTransaction,
  previewTransaction,
  TransactionDraft,
  TransactionForm
} from './transaction';

test('dollarsToCents parses money without float drift', () => {
  assert.equal(dollarsToCents('12.34'), 1234);
  assert.equal(dollarsToCents('0.1'), 10);
  assert.equal(dollarsToCents('1.005'), null);   // more than 2 decimals
  assert.equal(dollarsToCents('$50'), 5000);
  assert.equal(dollarsToCents('1,250.50'), 125050);
  assert.equal(dollarsToCents('-25'), -2500);
  assert.equal(dollarsToCents(''), null);
  assert.equal(dollarsToCents('abc'), null);
  ['1e3', '+25', '.5'].forEach(bad => assert.equal(dollarsToCents(bad), null, bad));
});

const draft = (over: Partial<TransactionForm>): TransactionForm => ({
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

// ── each kind maps to exactly one server call ────────────────────────────────

test('a payment becomes one record-payment call, invoice and reference nullable', () => {
  assert.deepEqual(
    planTransaction({ kind: 'Payment', memberId: 'm1', amountCents: 2500, method: 'cash' }),
    { call: 'recordPayment', body: { member_id: 'm1', amount_cents: 2500, method: 'cash', invoice_id: null, reference: null } }
  );
  assert.deepEqual(
    planTransaction({ kind: 'Payment', memberId: 'm1', amountCents: 2500, method: 'venmo', invoiceId: 'inv1', reference: 'TX9' }),
    { call: 'recordPayment', body: { member_id: 'm1', amount_cents: 2500, method: 'venmo', invoice_id: 'inv1', reference: 'TX9' } }
  );
});

test('a fine on an event goes through the event-fine endpoint; the server sets the amount', () => {
  assert.deepEqual(
    planTransaction({ kind: 'Fine', memberId: 'm1', amountCents: 2500, reason: '', eventId: 'e1' }),
    { call: 'issueEventFine', eventId: 'e1', memberIds: ['m1'] }
  );
});

test('a free-form fine is an invoice with source fine and the reason as description', () => {
  assert.deepEqual(
    planTransaction({ kind: 'Fine', memberId: 'm1', amountCents: 1500, reason: 'Missed chapter' }),
    { call: 'createInvoice', body: { member_id: 'm1', source: 'fine', amount_cents: 1500, description: 'Missed chapter' } }
  );
});

test('an invoice is a manual invoice', () => {
  assert.deepEqual(
    planTransaction({ kind: 'Invoice', memberId: 'm1', amountCents: 25000, description: 'Fall dues' }),
    { call: 'createInvoice', body: { member_id: 'm1', source: 'manual', amount_cents: 25000, description: 'Fall dues' } }
  );
});

test('an adjustment keeps its sign and is a manual correction', () => {
  assert.deepEqual(
    planTransaction({ kind: 'Adjustment', memberId: 'm1', deltaCents: -1000, reason: 'Fine issued in error' }),
    { call: 'createAdjustment', body: { member_id: 'm1', kind: 'manual_correction', delta_cents: -1000, reason: 'Fine issued in error' } }
  );
});

test('nothing is sent for zero or negative money', () => {
  for (const amountCents of [0, -500]) {
    assert.throws(() => planTransaction({ kind: 'Payment', memberId: 'm1', amountCents, method: 'cash' }), /more than \$0\.00/);
    assert.throws(() => planTransaction({ kind: 'Fine', memberId: 'm1', amountCents, reason: 'x' }), /more than \$0\.00/);
    assert.throws(() => planTransaction({ kind: 'Invoice', memberId: 'm1', amountCents, description: 'x' }), /more than \$0\.00/);
  }
  assert.throws(() => planTransaction({ kind: 'Adjustment', memberId: 'm1', deltaCents: 0, reason: 'x' }), /cannot be \$0\.00/);
});

test('a free-form fine, an invoice and an adjustment all need words', () => {
  assert.throws(() => planTransaction({ kind: 'Fine', memberId: 'm1', amountCents: 100, reason: '  ' }), /reason/i);
  assert.throws(() => planTransaction({ kind: 'Invoice', memberId: 'm1', amountCents: 100, description: '' }), /description/i);
  assert.throws(() => planTransaction({ kind: 'Adjustment', memberId: 'm1', deltaCents: 100, reason: '' }), /reason/i);
  assert.throws(() => planTransaction({ kind: 'Payment', memberId: '', amountCents: 100, method: 'cash' }), /member/i);
});
