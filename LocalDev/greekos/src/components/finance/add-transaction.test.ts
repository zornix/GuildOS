import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import AddTransactionModal from './AddTransactionModal';
import type { ChapterEvent, Member } from '../../types';
import type { TransactionAccess } from '../../lib/dues';

const member: Member = {
  id: 'm1', name: 'Jake Martinez', email: 'jake@example.test', phone: '',
  role: 'Active Member', status: 'Active', standing: 'Good Standing', gpa: 3.2,
  duesBalanceCents: 2500, duesBalance: 25, attendanceRate: 90, pledgeClass: "Fall '22"
};

const event: ChapterEvent = {
  id: 'e1', title: 'Chapter meeting', date: '2026-09-01', startTime: '19:00', endTime: '20:00',
  time: '7:00 PM', location: 'House', type: 'Chapter Meeting', audience: 'All Members',
  required: true, attendanceTaken: true, supervisors: [], organizers: [], jobs: []
};

const everything: TransactionAccess = { kinds: ['Payment', 'Fine', 'Invoice', 'Adjustment'], eventFines: true, freeFormFines: true };

function render(over: Partial<Parameters<typeof AddTransactionModal>[0]> = {}) {
  return renderToStaticMarkup(createElement(AddTransactionModal, {
    members: [member], events: [event], access: everything,
    onSubmit: async () => {}, onClose: () => {}, ...over
  }));
}

test('only the kinds the session may record are offered', () => {
  const html = render({ access: { kinds: ['Payment'], eventFines: false, freeFormFines: false } });
  assert.match(html, /value="Payment"/);
  assert.doesNotMatch(html, /value="Fine"|value="Invoice"|value="Adjustment"/);
  // A payment needs the method the server's pattern accepts.
  assert.match(html, /<option[^>]*value="venmo"/);
  assert.match(html, /<option[^>]*value="bank_transfer"/);
});

test('an event fine shows the flat amount read-only and offers no memo', () => {
  const html = render({ initial: { kind: 'Fine', eventId: 'e1' } });
  assert.match(html, /readonly/i);
  assert.match(html, /value="25\.00"/);
  assert.doesNotMatch(html, /Memo|Reason/);
});

test('a session that can only issue event fines gets no free-form option', () => {
  const html = render({ access: { kinds: ['Fine'], eventFines: true, freeFormFines: false }, initial: { kind: 'Fine' } });
  assert.match(html, /Chapter meeting/);
  assert.doesNotMatch(html, /No event/);
});

test('a payment opened from a fine locks the member and says what it pays first', () => {
  const html = render({
    title: 'Mark fine paid',
    note: 'Jake Martinez owes $25.00 for "Late to chapter".',
    initial: { kind: 'Payment', memberId: 'm1', amountDollars: '25.00', invoiceId: 'f1' }
  });
  assert.match(html, /Mark fine paid/);
  assert.match(html, /owes \$25\.00/);
  assert.match(html, /<select[^>]*disabled/);
  assert.match(html, /pays this invoice first/);
});
