import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EVENT_FILTER_TYPES, filterEventsByType, liveDoorEvent } from './events';
import type { ChapterEvent } from '../types';

const ev = (over: Partial<ChapterEvent>): ChapterEvent => ({
  id: 'e', title: 't', date: '2026-09-10', startTime: '18:00', endTime: '20:00', time: '',
  location: '', type: 'Chapter Meeting', audience: 'All Members', required: false,
  attendanceTaken: false, supervisors: [], organizers: [], jobs: [], ...over
});

test('filter list starts with All and matches the chips in the old filter card', () => {
  assert.deepEqual([...EVENT_FILTER_TYPES], ['All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education']);
});

test('All keeps every event; a type keeps only that type', () => {
  const list = [ev({ id: 'a', type: 'Social' }), ev({ id: 'b', type: 'Philanthropy' })];
  assert.deepEqual(filterEventsByType(list, 'All').map(e => e.id), ['a', 'b']);
  assert.deepEqual(filterEventsByType(list, 'Social').map(e => e.id), ['a']);
  assert.deepEqual(filterEventsByType(list, 'Brotherhood'), []);
});

test('liveDoorEvent is the earliest upcoming event with an open door link', () => {
  const list = [
    ev({ id: 'past', date: '2026-09-01', checkInLinkActive: true }),
    ev({ id: 'later', date: '2026-09-12', checkInLinkActive: true }),
    ev({ id: 'soon', date: '2026-09-08', checkInLinkActive: true }),
    ev({ id: 'closed', date: '2026-09-07', checkInLinkActive: false })
  ];
  assert.equal(liveDoorEvent(list, '2026-09-07')?.id, 'soon');
  assert.equal(liveDoorEvent([ev({ checkInLinkActive: false })], '2026-09-07'), undefined);
});
