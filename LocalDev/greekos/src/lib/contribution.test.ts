import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ContributionRecord,
  EMPTY_CONTRIBUTION,
  dateRangeLabel,
  resumeLine
} from './contribution';

const record = (over: Partial<ContributionRecord>): ContributionRecord => ({
  ...EMPTY_CONTRIBUTION,
  ...over
});
const ev = (attendeeCount: number, id = 'e') => ({
  eventId: id, title: 'Formal', date: '2026-03-01', attendeeCount
});

test('résumé line reads like a résumé line', () => {
  const line = resumeLine(record({
    eventsOrganized: [ev(200, 'a'), ev(140, 'b')],
    initiativesChaired: [{ initiativeId: 'i', title: 'Food drive', start: '2026-04-01', end: null }],
    jobsDone: [{ jobId: 'j', title: 'Setup', attachedTo: 'event', date: '2026-03-01' }],
    eventsAttendedCount: 9
  }));
  assert.equal(
    line,
    'Organized 2 events with 340 total attendees, chaired 1 initiative, completed 1 job, attended 9 events.'
  );
});

test('zero counts are left out, not printed as zeros', () => {
  assert.equal(resumeLine(record({ eventsAttendedCount: 1 })), 'Attended 1 event.');
  assert.equal(
    resumeLine(record({ eventsOrganized: [ev(0)] })),
    'Organized 1 event.'
  );
});

test('an empty record says so instead of claiming nothing', () => {
  assert.equal(resumeLine(EMPTY_CONTRIBUTION), 'No chapter record yet.');
});

test('date range collapses to the start date when there is no distinct end', () => {
  const base = { initiativeId: 'i', title: 't', start: '2026-04-01' };
  assert.equal(dateRangeLabel({ ...base, end: null }), '2026-04-01');
  assert.equal(dateRangeLabel({ ...base, end: '2026-04-01' }), '2026-04-01');
  assert.equal(dateRangeLabel({ ...base, end: '2026-04-05' }), '2026-04-01 – 2026-04-05');
});
