// src/selfcheck.ts — run: npx tsx src/selfcheck.ts   (exits non-zero on failure)
import assert from 'node:assert';
import { adaptTaskToJob, groupJobsByParent } from './adapters';
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
console.log('selfcheck OK');
