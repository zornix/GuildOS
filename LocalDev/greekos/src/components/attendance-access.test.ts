import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import AttendanceModule from './AttendanceModule';
import { can, isOfficerView } from '../lib/session';
import type { ChapterEvent, Excuse, Member } from '../types';

const noop = () => {};

const event: ChapterEvent = {
  id: 'e1', title: 'Weekly chapter', date: '2026-09-20',
  startTime: '19:00', endTime: '20:00', time: '19:00 - 20:00',
  location: 'House', type: 'Chapter Meeting', audience: 'All Members', required: true,
  attendanceTaken: false, supervisors: [], organizers: [], jobs: []
};

const member: Member = {
  id: 'm1', name: 'Test Brother', email: 'brother@example.test', phone: '',
  role: 'Active Member', status: 'Active', pledgeClass: 'Fall 2026', major: 'Economics',
  gpa: 3.4, standing: 'Good Standing', attendanceRate: 91,
  duesBalance: 0, duesBalanceCents: 0, securityHoursServed: 0
};

const excuse: Excuse = {
  id: 'x1', memberId: 'm1', memberName: 'Test Brother', eventId: 'e1',
  eventName: 'Weekly chapter', eventDate: '2026-09-20', reason: 'Midterm',
  status: 'Pending', submittedAt: '2026-09-18'
};

function attendance(permissions: string[], tab: 'roster_check' | 'excuses' | 'self_pin') {
  return renderToStaticMarkup(createElement(AttendanceModule, {
    events: [event], members: [member], excuses: [excuse],
    canMarkAttendance: can(permissions, 'attendance:override'),
    canReviewExcuses: can(permissions, 'attendance:excuse:review'),
    canSeeAttendanceRates: can(permissions, 'standing:view_all'),
    currentMemberName: 'Test Brother', initialTab: tab,
    onRecordAttendance: noop, onSubmitExcuse: noop, onReviewExcuse: noop,
    onSelfCheckIn: async () => ({ ok: true, message: '' })
  }));
}

test('roll call follows attendance:override, not officer presentation', () => {
  assert.equal(isOfficerView(['attendance:override']), false);
  assert.match(attendance(['attendance:override'], 'roster_check'), /Save roll call/);
  assert.doesNotMatch(attendance(['standing:view_all'], 'roster_check'), /Save roll call/);
});

test('excuse review follows attendance:excuse:review', () => {
  assert.match(attendance(['attendance:excuse:review'], 'excuses'), />Approve</);
  assert.doesNotMatch(attendance(['attendance:override'], 'excuses'), />Approve</);
});

test('the semester rate column follows standing:view_all', () => {
  assert.match(attendance(['standing:view_all'], 'roster_check'), /Semester rate/);
  assert.doesNotMatch(attendance(['attendance:override'], 'roster_check'), /Semester rate/);
});

test('each roll-call row is a named radio group with one roving tab stop', () => {
  const html = attendance(['attendance:override'], 'roster_check');
  assert.match(html, /role="radiogroup" aria-label="Attendance for Test Brother"/);
  // Unmarked row: the first option is the tab stop, the rest are reached with arrows.
  assert.match(html, /<button[^>]*role="radio"[^>]*aria-checked="false"[^>]*tabindex="0"[^>]*>Present</);
  assert.match(html, /<button[^>]*role="radio"[^>]*aria-checked="false"[^>]*tabindex="-1"[^>]*>Late</);
  assert.doesNotMatch(html, /aria-pressed/);
});
