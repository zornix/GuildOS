import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptTasks } from './adapters';
import type { TaskDto } from './api';
import type { Member } from './types';

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
