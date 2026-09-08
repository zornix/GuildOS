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
  ['1e3', '+25', '.5'].forEach(bad => assert.equal(dollarsToCents(bad), null, bad));
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
