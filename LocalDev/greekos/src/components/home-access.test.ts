import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import DashboardOverview from './DashboardOverview';
import { EMPTY_CONTRIBUTION } from '../lib/contribution';
import { can, isOfficerView } from '../lib/session';
import type { ChapterEvent } from '../types';

const noop = () => {};

const reportedJobEvent: ChapterEvent = {
  id: 'e1', title: 'Chapter Meeting', date: '2099-01-01', startTime: '18:00', endTime: '20:00', time: '',
  location: '', type: 'Chapter Meeting', audience: 'All Members', required: false, attendanceTaken: false,
  supervisors: [], organizers: [],
  jobs: [{ id: 'j1', title: 'Chairs', description: '', peopleNeeded: 1, claimants: [], status: 'Done Reported' }]
};

function home(permissions: string[], events: ChapterEvent[] = []) {
  return renderToStaticMarkup(createElement(DashboardOverview, {
    members: [], events, tasks: [], initiatives: [], announcements: [],
    officerView: isOfficerView(permissions),
    canScheduleEvent: can(permissions, 'calendar:event:create'),
    canManageJobs: can(permissions, 'tasks:assign'),
    canDeleteAnnouncement: can(permissions, 'announcements:create'),
    currentMemberId: 'm1', currentMemberName: 'Test Brother',
    contribution: EMPTY_CONTRIBUTION, myBalance: null,
    onNavigateTab: noop, onOpenEvent: noop, onScheduleEvent: noop,
    onVolunteerOrganizer: noop, onSelfCheckIn: async () => ({ ok: true, message: '' }),
    onDeleteAnnouncement: noop
  }));
}

test('Schedule event follows calendar:event:create, not officer presentation', () => {
  assert.match(home(['calendar:event:create']), /Schedule event/);
  assert.doesNotMatch(home(['standing:view_all']), /Schedule event/);
});

test('the sign-off nudge follows tasks:assign, the key behind the approve button it points at', () => {
  assert.match(home(['tasks:assign'], [reportedJobEvent]), /waiting for your sign-off/);
  assert.doesNotMatch(home(['standing:view_all'], [reportedJobEvent]), /waiting for your sign-off/);
  assert.doesNotMatch(home(['tasks:assign']), /waiting for your sign-off/);
});

test('the door-code section is the member presentation of Home', () => {
  assert.match(home([]), /No door open right now/);
  assert.doesNotMatch(home(['standing:view_all']), /No door open right now/);
});
