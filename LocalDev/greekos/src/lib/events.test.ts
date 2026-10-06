import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EVENT_FILTER_TYPES, eventDeleteMessage, filterEventsByType, liveDoorEvent } from './events';
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

test('liveDoorEvent is the earliest upcoming event with an open door code', () => {
  const list = [
    ev({ id: 'past', date: '2026-09-01', checkInLinkActive: true }),
    ev({ id: 'later', date: '2026-09-12', checkInLinkActive: true }),
    ev({ id: 'soon', date: '2026-09-08', checkInLinkActive: true }),
    ev({ id: 'closed', date: '2026-09-07', checkInLinkActive: false })
  ];
  assert.equal(liveDoorEvent(list, '2026-09-07')?.id, 'soon');
  // Today's own door counts as upcoming, and beats a later day.
  const openToday = ev({ id: 'today', date: '2026-09-07', checkInLinkActive: true });
  assert.equal(liveDoorEvent([...list, openToday], '2026-09-07')?.id, 'today');
  assert.equal(liveDoorEvent([ev({ checkInLinkActive: false })], '2026-09-07'), undefined);
});

test('deleting an event says whether it was deleted or cancelled (D4)', () => {
  assert.equal(eventDeleteMessage({ deleted: true, cancelled: false }), 'Event deleted.');
  assert.equal(
    eventDeleteMessage({ deleted: false, cancelled: true }),
    'Event cancelled. Its attendance and fines were kept.'
  );
});
