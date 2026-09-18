import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import FinanceModule, { treasuryAbilities } from './FinanceModule';
import { isOfficerView } from '../lib/session';

const noop = () => {};
const asyncNoop = async () => {};

function treasury(permissions: string[]) {
  return renderToStaticMarkup(createElement(FinanceModule, {
    members: [], fines: [], payments: [], ledger: [],
    permissions: new Set(permissions),
    chapterName: 'Alpha', currentMemberName: 'Treasurer',
    myBalance: null, myInvoices: [],
    pendingProofCentsOf: () => 0, submissions: [], queueLoading: false,
    onRefreshQueue: asyncNoop, onCreateDuesRun: asyncNoop, onSubmitProof: asyncNoop,
    onVerifyProof: asyncNoop, onRejectProof: asyncNoop,
    onOpenEvidence: async () => '',
    balanceCentsOf: () => 0,
    onRecordPayment: noop, onIssueFine: noop, onPostInvoice: noop,
    onApproveFinePayment: noop, onPostLedgerCorrection: noop
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
  assert.doesNotMatch(html, /Pay balance/);
});

test('a member with no treasury key sees only their own payment controls', () => {
  const abilities = treasuryAbilities(new Set(['standing:view_all']));
  assert.equal(abilities.isTreasuryOfficer, false);

  const html = treasury(['standing:view_all']);
  assert.match(html, /Pay balance/);
  assert.doesNotMatch(html, /New dues run|Add transaction|Proof queue/);
});
