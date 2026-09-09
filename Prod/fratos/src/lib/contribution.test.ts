import { test } from 'node:test';
import assert from 'node:assert/strict';
import { upcomingContribution } from './contribution';
import type { ChapterEvent, Initiative } from '../types';

const event = (over: Partial<ChapterEvent>): ChapterEvent => ({
  id: 'e', title: 't', date: '2026-09-10', startTime: '18:00', endTime: '20:00', time: '18:00 - 20:00',
  location: '', type: 'Chapter Meeting', audience: 'All Members', required: false, attendanceTaken: false,
  supervisors: [], organizers: [], jobs: [], ...over
});
const initiative = (over: Partial<Initiative>): Initiative => ({
  id: 'i', title: 't', description: '', leadChairs: [], category: 'Philanthropy',
  startDate: '2026-09-01', targetDate: '2026-09-30', status: 'Active', jobs: [], ...over
});

test('counts only upcoming events the member organizes or supervises', () => {
  const events = [
    event({ id: 'a', date: '2026-09-10', organizers: ['Jake Martinez'] }),
    event({ id: 'b', date: '2026-09-11', supervisors: ['Jake Martinez'], organizers: ['Jake Martinez'] }),
    event({ id: 'c', date: '2026-09-01', organizers: ['Jake Martinez'] }), // past
    event({ id: 'd', date: '2026-09-12', organizers: ['Someone Else'] })
  ];
  const s = upcomingContribution('Jake Martinez', events, [], '2026-09-07');
  assert.deepEqual(s, { scope: 'upcoming', eventsOrganized: 2, eventsSupervised: 1, initiativesChaired: 0 });
});

test('today counts as upcoming', () => {
  const s = upcomingContribution('J', [event({ date: '2026-09-07', supervisors: ['J'] })], [], '2026-09-07');
  assert.equal(s.eventsSupervised, 1);
});

test('counts initiatives chaired that have not ended', () => {
  const inits = [
    initiative({ id: 'x', leadChairs: ['J'], targetDate: '2026-09-30' }),
    initiative({ id: 'y', leadChairs: ['J'], targetDate: '2026-08-01' }), // ended
    initiative({ id: 'z', leadChairs: ['K'] })
  ];
  assert.equal(upcomingContribution('J', [], inits, '2026-09-07').initiativesChaired, 1);
});

test('empty name never matches', () => {
  const s = upcomingContribution('', [event({ organizers: [''] })], [], '2026-09-07');
  assert.equal(s.eventsOrganized, 0);
});
