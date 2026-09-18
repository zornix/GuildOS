import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import InitiativesModule from './InitiativesModule';
import { can, isOfficerView } from '../lib/session';
import type { Initiative, Member } from '../types';

const noop = () => {};
const members = [{ id: 'm1', name: 'Ryan Cole' }] as Member[];

const initiative: Initiative = {
  id: 'i1', title: 'Homecoming build', description: '', category: 'Philanthropy',
  status: 'Active', leadChairs: [], startDate: '2026-09-01', targetDate: '2026-10-01',
  jobs: [{
    id: 'j1', title: 'Order lumber', description: '', peopleNeeded: 1,
    status: 'To Do', claimants: []
  }]
};

function initiatives(permissions: string[]) {
  return renderToStaticMarkup(createElement(InitiativesModule, {
    initiatives: [initiative], members, currentMemberName: 'Ryan Cole',
    canCreateInitiative: can(permissions, 'calendar:initiative:create'),
    canManageJobs: can(permissions, 'tasks:assign'),
    onAddInitiative: noop, onAddJobToInitiative: noop, onClaimInitiativeJob: noop,
    onUnclaimInitiativeJob: noop, onReportInitiativeJobDone: noop, onApproveInitiativeJob: noop
  }));
}

test('launching an initiative follows calendar:initiative:create', () => {
  assert.equal(isOfficerView(['calendar:initiative:create']), false);
  assert.match(initiatives(['calendar:initiative:create']), /Launch New Initiative/);
  assert.doesNotMatch(initiatives(['standing:view_all']), /Launch New Initiative/);
});

test('adding a job to an initiative follows tasks:assign', () => {
  assert.match(initiatives(['tasks:assign']), /Add job/);
  assert.doesNotMatch(initiatives(['standing:view_all']), /Add job/);
});
