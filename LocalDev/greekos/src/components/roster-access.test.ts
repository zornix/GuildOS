import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RosterModule from './RosterModule';
import { can, isOfficerView } from '../lib/session';
import type { Member } from '../types';

const member: Member = {
  id: 'm1', name: 'Test Brother', email: 'brother@example.test', phone: '',
  role: 'Active Member', status: 'Active', pledgeClass: 'Fall 2026', major: 'Economics',
  gpa: 3.4, standing: 'Good Standing', attendanceRate: 91,
  duesBalance: 0, duesBalanceCents: 0, securityHoursServed: 0
};

function roster(permissions: string[]) {
  return renderToStaticMarkup(createElement(RosterModule, {
    members: [member],
    canInviteMembers: can(permissions, 'members:invite'),
    canSeeStandingDetail: can(permissions, 'standing:view_all'),
    canAssignRoles: can(permissions, 'roles:assign'),
    canSeeSmsConsent: can(permissions, 'members:invite'),
    onImportRoster: async () => ({ created_count: 0, skipped_count: 0, created: [], skipped: [] }),
  }));
}

test('CSV import follows members:invite without a fake add-member control', () => {
  assert.equal(isOfficerView(['members:invite']), false);
  const html = roster(['members:invite']);
  assert.doesNotMatch(html, /Add Member/);
  assert.match(html, /CSV/i);
  assert.doesNotMatch(roster(['standing:view_all']), /Add Member/);
});

test('standing is read-only even with standing:update', () => {
  assert.doesNotMatch(roster(['standing:update']), /<select/);
  assert.doesNotMatch(roster(['members:invite']), /Academic Probation/);
});

test('the attendance column follows standing:view_all', () => {
  assert.match(roster(['standing:view_all']), /91%/);
  assert.doesNotMatch(roster(['members:invite']), /91%/);
});
