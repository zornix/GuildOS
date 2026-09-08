import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptMemberBalance, balanceStatusLine } from './balance';

test('adapts outstanding cents and invoice counts', () => {
  const b = adaptMemberBalance({
    member_id: 'm1',
    balance: { outstanding_balance_cents: 12500, current_balance_cents: 12500, total_owed_cents: 30000, total_paid_cents: 17500 },
    pending_cents: 0,
    pending_submissions: [],
    open_invoices: [
      { id: 'i1', description: 'Fall dues', amount_cents: 10000, remaining_cents: 10000, due_at: '2026-09-01T00:00:00Z', overdue: true, source: 'dues', status: 'open' },
      { id: 'i2', description: 'Fine', amount_cents: 2500, remaining_cents: 2500, due_at: null, overdue: false, source: 'fine', status: 'open' }
    ],
    recent_activity: []
  });
  assert.deepEqual(b, { outstandingCents: 12500, openInvoiceCount: 2, overdueInvoiceCount: 1 });
});

test('a clean account is all zeros', () => {
  const b = adaptMemberBalance({
    member_id: 'm1',
    balance: { outstanding_balance_cents: 0, current_balance_cents: 0, total_owed_cents: 0, total_paid_cents: 0 },
    pending_cents: 0, pending_submissions: [], open_invoices: [], recent_activity: []
  });
  assert.deepEqual(b, { outstandingCents: 0, openInvoiceCount: 0, overdueInvoiceCount: 0 });
});

test('balance line names the amount and invoice counts', () => {
  assert.equal(
    balanceStatusLine({ outstandingCents: 12500, openInvoiceCount: 2, overdueInvoiceCount: 1 }),
    'Balance owed $125.00 · 2 open invoices (1 overdue)'
  );
  assert.equal(
    balanceStatusLine({ outstandingCents: 2500, openInvoiceCount: 1, overdueInvoiceCount: 0 }),
    'Balance owed $25.00 · 1 open invoice'
  );
});

test('a clean account says so; unknown says nothing', () => {
  assert.equal(balanceStatusLine({ outstandingCents: 0, openInvoiceCount: 0, overdueInvoiceCount: 0 }), 'No balance owed');
  assert.equal(balanceStatusLine(null), '');
});
