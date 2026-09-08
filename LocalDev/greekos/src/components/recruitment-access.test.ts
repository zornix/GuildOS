import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Sidebar from './Sidebar';
import RecruitmentModule from './RecruitmentModule';
import { can, isOfficerView } from '../lib/session';
import type { PNM } from '../types';

const viewKey = 'recruitment:pipeline:view';
const updateKey = 'recruitment:pipeline:update';
const noop = () => {};

function navigation(permissions: string[], isOfficer = isOfficerView(permissions)) {
  return renderToStaticMarkup(createElement(Sidebar, {
    activeTab: 'dashboard', setActiveTab: noop,
    permissions: new Set(permissions), isOfficer, setIsOfficer: noop,
    currentMemberName: 'Recruitment Chair', setCurrentMemberName: noop,
    allMembers: [], open: true, onClose: noop,
  }));
}

const prospect: PNM = {
  id: 'p1', name: 'Test Prospect', email: 'prospect@example.test', phone: '',
  major: '', gpa: 3.5, year: 'Freshman', hometown: '', notes: '',
  eventsAttended: 0, votesFor: 0, votesAgainst: 0, status: 'Prospect',
};

function recruitment(permissions: string[]) {
  return renderToStaticMarkup(createElement(RecruitmentModule, {
    pnms: [prospect], canUpdate: can(permissions, updateKey),
    onAddPNM: noop, onVotePNM: noop, onExtendBid: noop,
  }));
}

test('recruitment chair sees Recruitment and can manage prospects without standing:view_all', () => {
  const permissions = [viewKey, updateKey];
  assert.equal(isOfficerView(permissions), false);
  assert.match(navigation(permissions), />Recruitment</);
  const html = recruitment(permissions);
  assert.match(html, /Add Prospect \(PNM\)/);
  assert.match(html, /Extend bid/);
  assert.match(html, /Vote For/);
});

test('pipeline viewer sees prospects without create, vote or bid controls', () => {
  assert.match(navigation([viewKey]), />Recruitment</);
  const html = recruitment([viewKey]);
  assert.match(html, /Test Prospect/);
  assert.doesNotMatch(html, /Add Prospect|Extend bid|Vote For/);
});

test('standing or demo officer mode cannot grant module navigation permissions', () => {
  assert.doesNotMatch(navigation(['standing:view_all']), />Recruitment</);
  assert.doesNotMatch(navigation([], true), />Recruitment</);
  assert.doesNotMatch(navigation([], true), />Command console</);
});

test('module access survives the presentation-only Demo Member view', () => {
  const html = navigation(['standing:view_all', viewKey, 'nl_controller:execute'], false);
  assert.match(html, />Recruitment</);
  assert.match(html, />Command console</);
});
