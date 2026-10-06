import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import FinanceModule, { treasuryAbilities } from './FinanceModule';
import { isOfficerView } from '../lib/session';

const asyncNoop = async () => {};

function treasury(permissions: string[]) {
  return renderToStaticMarkup(createElement(FinanceModule, {
    members: [], fines: [], payments: [], events: [],
    permissions: new Set(permissions),
    chapterName: 'Alpha', currentMemberName: 'Treasurer',
    myInvoices: [],
    pendingProofCentsOf: () => 0, submissions: [], queueLoading: false,
    onRefreshQueue: asyncNoop, onCreateDuesRun: asyncNoop, onSubmitProof: asyncNoop,
    onVerifyProof: asyncNoop, onRejectProof: asyncNoop,
    onOpenEvidence: async () => '',
    balanceCentsOf: () => 0,
    onSubmitTransaction: asyncNoop
  }));
}

test('a treasurer without standing:view_all still gets the treasury officer controls', () => {
  const permissions = [
    'treasury:invoice:create', 'treasury:payment:verify',
    'treasury:fines:issue', 'treasury:adjustment:create'
  ];
  assert.equal(isOfficerView(permissions), false);

  const abilities = treasuryAbilities(new Set(permissions));
  assert.deepEqual(abilities, {
    canCreateDuesRun: true, canVerifyPayments: true,
    canIssueFines: true, canPostAdjustment: true, isTreasuryOfficer: true
  });

  const html = treasury(permissions);
  assert.match(html, /New dues run/);
  assert.match(html, /Add transaction/);
  assert.match(html, /Proof queue/);
  // No server read backs a chapter-wide ledger, so nothing pretends to be one.
  assert.doesNotMatch(html, /Chapter ledger|demo/i);
});

test('a member with no treasury key pays through their invoices and sees no officer control', () => {
  const abilities = treasuryAbilities(new Set(['standing:view_all']));
  assert.equal(abilities.isTreasuryOfficer, false);

  const html = treasury(['standing:view_all']);
  assert.match(html, /My invoices/);
  assert.doesNotMatch(html, /New dues run|Add transaction|Proof queue|Pay balance|Mark paid/i);
});

test('holding only the verify key offers Add transaction (payments) but not a dues run', () => {
  const html = treasury(['treasury:payment:verify']);
  assert.match(html, /Add transaction/);
  assert.doesNotMatch(html, /New dues run/);
});
