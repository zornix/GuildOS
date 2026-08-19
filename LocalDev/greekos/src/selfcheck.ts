// src/selfcheck.ts — run: npx tsx src/selfcheck.ts   (exits non-zero on failure)
import assert from 'node:assert';
import { adaptTaskToJob, groupJobsByParent } from './adapters';
import { hasStarted, isoDay, isWithin36Hours, monthCells } from './formatters';
import type { TaskDto } from './api';
import type { Member } from './types';

const member = { id: 'm1', name: 'Ryan Cole' } as Member;
const membersById = new Map([['m1', member]]);
const base: TaskDto = {
  id: 't1', title: 'Setup chairs', description: 'front lawn', status: 'open',
  kind: 'standard', event_id: 'e1', initiative_id: null, people_needed: 3,
  claimants: [], claimed_count: 0, due_at: null,
} as TaskDto;

// status + claimant mapping
const open = adaptTaskToJob(base, membersById);
assert.equal(open.status, 'To Do');
assert.equal(open.peopleNeeded, 3);
const claimed = adaptTaskToJob({ ...base, status: 'in_progress', claimants: ['m1'], claimed_count: 1 }, membersById);
assert.equal(claimed.status, 'In Progress');
assert.deepEqual(claimed.claimants.map(c => c.memberName), ['Ryan Cole']);
assert.equal(adaptTaskToJob({ ...base, status: 'done_reported' }, membersById).status, 'Done Reported');
assert.equal(adaptTaskToJob({ ...base, status: 'approved' }, membersById).status, 'Approved');

// grouping: cancelled + security rows dropped, parents split
const grouped = groupJobsByParent([
  base,
  { ...base, id: 't2', status: 'cancelled' },
  { ...base, id: 't3', kind: 'security' },
  { ...base, id: 't4', event_id: null, initiative_id: 'i1' },
], membersById);
assert.deepEqual(grouped.byEvent.get('e1')!.map(j => j.id), ['t1']);
assert.deepEqual(grouped.byInitiative.get('i1')!.map(j => j.id), ['t4']);

// date rules: local day, month grid, T-36h unclaim lock
assert.equal(isoDay(new Date(2026, 6, 4)), '2026-07-04');
const july2026 = monthCells(2026, 6); // July 1 2026 is a Wednesday -> 3 blanks
assert.equal(july2026.length, 3 + 31);
assert.equal(july2026[0], null);
assert.equal(july2026[3], '2026-07-01');
assert.equal(july2026[33], '2026-07-31');
assert.equal(monthCells(2024, 1).filter(Boolean).length, 29); // leap February

const start = new Date('2026-07-13T18:00').getTime();
const hours = (n: number) => n * 60 * 60 * 1000;
assert.equal(isWithin36Hours('2026-07-13', '18:00', start - hours(40)), false);
assert.equal(isWithin36Hours('2026-07-13', '18:00', start - hours(10)), true);
assert.equal(isWithin36Hours('2026-07-13', '18:00', start + hours(2)), true); // started: stays locked
assert.equal(hasStarted('2026-07-13', '18:00', start - hours(10)), false);
assert.equal(hasStarted('2026-07-13', '18:00', start + hours(2)), true);

console.log('selfcheck OK');
