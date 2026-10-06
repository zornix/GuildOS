import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptFines, adaptTasks } from './adapters';
import type { FineDto, TaskDto } from './api';
import type { Member } from './types';
import { canClaimTask } from './lib/tasks';

const row = (over: Partial<TaskDto>): TaskDto => ({
  id: 't1', title: 'Setup chairs', description: null, assigned_member_id: null, status: 'open', required: false,
  due_at: null, created_at: '2026-09-01T00:00:00Z', event_id: null, initiative_id: null, kind: 'standard',
  people_needed: 1, claimants: [], claimed_count: 0, ...over
} as TaskDto);
const members = [{ id: 'm1', name: 'Ryan Cole' } as Member];

test('standalone jobs have no parent; attached jobs name theirs', () => {
  const titles = { events: new Map([['e1', 'Chapter Meeting']]), initiatives: new Map([['i1', 'Coat Drive']]) };
  const tasks = adaptTasks([
    row({ id: 'a' }),
    row({ id: 'b', event_id: 'e1' }),
    row({ id: 'c', initiative_id: 'i1' })
  ], members, titles);
  assert.equal(tasks[0].parent, undefined);
  assert.deepEqual(tasks[1].parent, { kind: 'event', title: 'Chapter Meeting' });
  assert.deepEqual(tasks[2].parent, { kind: 'initiative', title: 'Coat Drive' });
});

test('an attached job whose parent is unknown still says which kind', () => {
  const [t] = adaptTasks([row({ event_id: 'missing' })], members);
  assert.deepEqual(t.parent, { kind: 'event', title: 'Event' });
});

test('security shifts are not jobs on the board', () => {
  assert.equal(adaptTasks([row({ kind: 'security' }), row({ id: 'x' })], members).length, 1);
});

test('claimed jobs preserve ownership and capacity even without an assigned member', () => {
  const [task] = adaptTasks([row({ status: 'in_progress', claimants: ['m1'], claimed_count: 1, people_needed: 2 })], members);
  assert.equal(task.assignedTo, 'Ryan Cole');
  assert.equal(task.assignedToId, undefined);
  assert.equal(task.peopleNeeded, 2);
  assert.equal(task.claimedCount, 1);
  assert.equal(canClaimTask(task, 'm1'), false);
  assert.equal(canClaimTask(task, 'm2'), true);

  const [full] = adaptTasks([row({ claimants: ['m1'], claimed_count: 1 })], members);
  assert.equal(canClaimTask(full, 'm2'), false);
});

test('reported, approved, completed and cancelled jobs retain their lifecycle and cannot be claimed', () => {
  const statuses = { done_reported: 'Done Reported', approved: 'Approved', done: 'Completed', cancelled: 'Cancelled' };
  for (const [status, label] of Object.entries(statuses)) {
    const [task] = adaptTasks([row({ status })], members);
    assert.equal(task.status, label);
    assert.equal(canClaimTask(task, 'm1'), false, status);
  }
});

test('unknown states cannot accidentally become open jobs', () => {
  const [task] = adaptTasks([row({ status: 'future_state' })], members);
  assert.equal(task.status, 'Unknown');
  assert.equal(canClaimTask(task, 'm1'), false);
});

test('claiming requires an identified member and respects the server capacity summary', () => {
  const [task] = adaptTasks([row({})], members);
  assert.equal(canClaimTask(task, undefined), false);
  assert.equal(canClaimTask(task, 'm1'), true);
  const [full] = adaptTasks([row({ claimed_count: 1, claimants: [] })], members);
  assert.equal(canClaimTask(full, 'm1'), false);
});

test('a fine carries what is still owed, not just its face amount', () => {
  const row: FineDto = {
    id: 'f1', amount_cents: 2500, remaining_cents: 1500, status: 'partially_paid', reason: 'Late',
    issued_at: '2026-10-01T00:00:00Z', member_id: 'm1', member_name: 'Jake', event_id: null, event_title: null, event_date: null
  };
  const [fine] = adaptFines([row], []);
  assert.equal(fine.amountCents, 2500);
  assert.equal(fine.remainingCents, 1500);
});
