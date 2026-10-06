import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import EventsModule from './EventsModule';
import EventsBar from './EventsBar';
import { can, isOfficerView } from '../lib/session';
import type { ChapterEvent, Member } from '../types';

const noop = () => {};

const member: Member = {
  id: 'm1', name: 'Test Brother', email: 'brother@example.test', phone: '',
  role: 'Active Member', status: 'Active', pledgeClass: 'Fall 2026', major: 'Economics',
  gpa: 3.4, standing: 'Good Standing', attendanceRate: 100,
  duesBalance: 0, duesBalanceCents: 0, securityHoursServed: 0
};

const event: ChapterEvent = {
  id: 'e1', title: 'Weekly chapter', date: '2099-09-20',
  startTime: '19:00', endTime: '20:00', time: '19:00 - 20:00',
  location: 'House', type: 'Chapter Meeting', audience: 'All Members', required: true,
  attendanceTaken: false, supervisors: [], organizers: [],
  jobs: [{
    id: 'j1', title: 'Set up chairs', description: '', peopleNeeded: 1,
    status: 'To Do', claimants: []
  }]
};

function events(permissions: string[]) {
  return renderToStaticMarkup(createElement(EventsModule, {
    events: [event], members: [member],
    canCreateEvent: can(permissions, 'calendar:event:create'),
    canManageEvent: can(permissions, 'calendar:event:update'),
    canDeleteEvent: can(permissions, 'calendar:event:delete'),
    canManageCheckInLink: can(permissions, 'attendance:checkin_link:manage'),
    canManageJobs: can(permissions, 'tasks:assign'),
    currentMemberName: 'Test Brother',
    filterType: 'All', createOpen: false, onCreateOpenChange: noop,
    selectedEventId: 'e1', onSelectEventId: noop, onSelectEvent: noop,
    onAddEvent: noop, onUpdateEvent: noop, onDeleteEvent: noop, onVolunteerOrganizer: noop,
    onClaimJob: noop, onUnclaimJob: noop, onReportJobDone: noop,
    onApproveJob: noop, onRejectJob: noop, onAddJobToEvent: noop,
    onEditJob: noop, onDeleteJob: noop, onSendEventNotifyBlast: noop,
    onToggleCheckInLink: noop, onAssignSecurity: noop,
    onRequestSecuritySwap: noop, onRespondSecuritySwap: noop, onCancelSecuritySwap: noop
  }));
}

function bar(permissions: string[]) {
  return renderToStaticMarkup(createElement(EventsBar, {
    view: 'list', onViewChange: noop, filterType: 'All', onFilterChange: noop,
    canCreateEvent: can(permissions, 'calendar:event:create'), onCreate: noop
  }));
}

test('creating an event follows calendar:event:create', () => {
  assert.equal(isOfficerView(['calendar:event:create']), false);
  assert.match(bar(['calendar:event:create']), /Create event/);
  assert.doesNotMatch(bar(['standing:view_all']), /Create event/);
});

test('job management follows tasks:assign', () => {
  const html = events(['tasks:assign']);
  assert.match(html, /Add Job/);
  assert.match(html, />Edit</);
  assert.doesNotMatch(events(['standing:view_all']), /Add Job/);
});

test('the check-in link follows attendance:checkin_link:manage', () => {
  assert.match(events(['attendance:checkin_link:manage']), /Open door code/);
  assert.doesNotMatch(events(['standing:view_all']), /Open door code/);
});

test('assigning security follows calendar:event:update', () => {
  assert.match(events(['calendar:event:update']), /Assign Member/);
  assert.doesNotMatch(events(['standing:view_all']), /Assign Member/);
});
