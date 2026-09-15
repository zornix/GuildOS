import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RosterModule from './RosterModule';
import { toggleRoleKeys } from './MemberRolesPanel';
import { can } from '../lib/session';
import type { Member } from '../types';

const noop = () => {};

const member: Member = {
  id: 'm1', name: 'Test Brother', email: 'brother@example.test', phone: '',
  role: 'Active Member', status: 'Active', pledgeClass: 'Fall 2026', major: 'Economics',
  gpa: 3.4, standing: 'Good Standing', attendanceRate: 100,
  duesBalance: 0, duesBalanceCents: 0, securityHoursServed: 0,
};

function roster(permissions: string[]) {
  return renderToStaticMarkup(createElement(RosterModule, {
    members: [member], isOfficer: true,
    canAssignRoles: can(permissions, 'roles:assign'),
    onAddMember: noop, onUpdateStanding: noop,
  }));
}

test('toggling a role adds or removes exactly that key, without duplicates', () => {
  assert.deepEqual(toggleRoleKeys([], 'treasurer', true), ['treasurer']);
  assert.deepEqual(toggleRoleKeys(['president'], 'treasurer', true), ['president', 'treasurer']);
  assert.deepEqual(toggleRoleKeys(['president', 'treasurer'], 'treasurer', false), ['president']);
  assert.deepEqual(toggleRoleKeys(['treasurer'], 'treasurer', true), ['treasurer']);
  assert.deepEqual(toggleRoleKeys(['president'], 'treasurer', false), ['president']);
});

test('the Roles control needs roles:assign, not officer presentation', () => {
  assert.match(roster(['roles:assign']), />Roles</);
  assert.doesNotMatch(roster(['standing:view_all']), />Roles</);
});
