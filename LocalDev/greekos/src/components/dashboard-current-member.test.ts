import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import DashboardOverview from './DashboardOverview';
import { EMPTY_CONTRIBUTION } from '../lib/contribution';
import type { Member } from '../types';

const noop = () => {};

function member(id: string, smsConsent: boolean): Member {
  return {
    id, name: 'Same Name', email: `${id}@example.test`, phone: '',
    role: 'Active Member', status: 'Active', pledgeClass: 'Fall 2026', major: 'Economics',
    gpa: 3.4, standing: 'Good Standing', attendanceRate: 100,
    duesBalance: 0, duesBalanceCents: 0, securityHoursServed: 0, smsConsent
  };
}

function home(currentMemberId: string) {
  return renderToStaticMarkup(createElement(DashboardOverview, {
    members: [member('m1', false), member('m2', true)],
    events: [], tasks: [], initiatives: [], announcements: [],
    officerView: false, canScheduleEvent: false, canManageJobs: false, canDeleteAnnouncement: false,
    currentMemberId, currentMemberName: 'Same Name',
    contribution: EMPTY_CONTRIBUTION, myBalance: null,
    onNavigateTab: noop, onOpenEvent: noop, onScheduleEvent: noop,
    onVolunteerOrganizer: noop, onSelfCheckIn: async () => ({ ok: true, message: '' }),
    onDeleteAnnouncement: noop
  }));
}

test('the consent card follows the signed-in member id, not a shared name', () => {
  assert.match(home('m2'), />On</);
  assert.match(home('m1'), />Off</);
});
