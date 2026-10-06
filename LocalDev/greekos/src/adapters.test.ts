import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  adaptCheckInLink, adaptEventDetail, adaptFines, adaptPayments, adaptSecurityAssignment, adaptTaskToJob, adaptTasks,
  adaptUpcomingDetails, groupJobsByParent
} from './adapters';
import type { EventDetailDto, FineDto, SecurityAssignmentDto, TaskDto, UpcomingDetailsDto } from './api';
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

test('adaptTaskToJob maps status and claimants; groupJobsByParent drops cancelled and security rows', () => {
  const membersById = new Map(members.map(m => [m.id, m]));
  const base = row({ event_id: 'e1', people_needed: 3 });
  const open = adaptTaskToJob(base, membersById);
  assert.equal(open.status, 'To Do');
  assert.equal(open.peopleNeeded, 3);
  const claimed = adaptTaskToJob({ ...base, status: 'in_progress', claimants: ['m1'], claimed_count: 1 }, membersById);
  assert.equal(claimed.status, 'In Progress');
  assert.deepEqual(claimed.claimants.map(c => c.memberName), ['Ryan Cole']);
  assert.equal(adaptTaskToJob({ ...base, status: 'done_reported' }, membersById).status, 'Done Reported');
  assert.equal(adaptTaskToJob({ ...base, status: 'approved' }, membersById).status, 'Approved');

  const grouped = groupJobsByParent([
    base,
    { ...base, id: 't2', status: 'cancelled' },
    { ...base, id: 't3', kind: 'security' },
    { ...base, id: 't4', event_id: null, initiative_id: 'i1' }
  ], membersById);
  assert.deepEqual(grouped.byEvent.get('e1')!.map(j => j.id), ['t1']);
  assert.deepEqual(grouped.byInitiative.get('i1')!.map(j => j.id), ['t4']);
});

test('a code-less check-in link (member view) still reads as an open door; {} is closed', () => {
  assert.deepEqual(
    adaptCheckInLink({ event_id: 'e1', active: true, expires_at: '2026-09-20T20:00:00Z' }),
    { checkInLinkActive: true, checkInToken: undefined }
  );
  assert.deepEqual(
    adaptCheckInLink({ short_code: 'A7x9Kp', url: 'http://h/c/A7x9Kp', expires_at: '2026-09-20T20:00:00Z' }),
    { checkInLinkActive: true, checkInToken: 'A7x9Kp' }
  );
  assert.deepEqual(adaptCheckInLink({}), { checkInLinkActive: false, checkInToken: undefined });
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

test('a payment shows the method the server recorded and no invented type', () => {
  const base = { id: 'p1', member_id: 'm1', invoice_id: null, amount_cents: 5000, created_at: '2026-10-01T00:00:00Z' };
  const [venmo, unknown] = adaptPayments([{ ...base, method: 'bank_transfer' }, base], []);
  assert.equal(venmo.paymentMethod, 'Bank transfer');
  assert.equal(unknown.paymentMethod, '—');
  assert.equal('type' in venmo, false);
});

test('the bulk upcoming read builds the same maps as the per-event requests did', () => {
  const roster = [{ id: 'm1', name: 'Ryan Cole' } as Member, { id: 'm2', name: 'Ali Shah' } as Member];
  const byId = new Map(roster.map(m => [m.id, m]));
  const detail = (id: string): EventDetailDto => ({
    id, title: 'Meeting', date: '2026-10-10', time: '19:00:00', location: 'Hall', required: true,
    attendance_count: 3, supervisors: [{ member_id: 'm1', is_creator: true, name: 'Ryan Cole' }],
    organizers: [{ id: 'o1', member_id: 'm2', source: 'volunteer', created_at: '2026-10-01T00:00:00Z' }],
    last_notified_at: null
  });
  const shift: SecurityAssignmentDto = {
    task_id: 't1', event_id: 'e1', member_id: 'm2', status: 'in_progress', rejection_reason: null,
    pending_swap: { id: 's1', task_id: 't1', event_id: 'e1', requester_member_id: 'm2', target_member_id: 'm1',
      note: null, status: 'pending', created_at: null }
  };
  const dto: UpcomingDetailsDto = { events: [
    { event_id: 'e1', detail: detail('e1'), security: [shift], checkin_link: {} },
    { event_id: 'e2', detail: detail('e2'), security: [],
      checkin_link: { event_id: 'e2', active: true, expires_at: '2026-10-10T20:00:00Z' } }
  ] };
  const { securityByEvent, detailByEvent } = adaptUpcomingDetails(dto, roster, byId);
  assert.deepEqual(securityByEvent.get('e1'), [adaptSecurityAssignment(shift, byId)]);
  assert.deepEqual(securityByEvent.get('e2'), []);
  assert.deepEqual(detailByEvent.get('e1'), { ...adaptEventDetail(detail('e1'), roster), ...adaptCheckInLink({}) });
  assert.deepEqual(detailByEvent.get('e2'), {
    ...adaptEventDetail(detail('e2'), roster), checkInLinkActive: true, checkInToken: undefined
  });
  assert.equal(detailByEvent.size, 2);
});

test('a cancelled fine reads as waived, not paid', () => {
  const row: FineDto = {
    id: 'f2', amount_cents: 2500, remaining_cents: 0, status: 'cancelled', reason: 'Late',
    issued_at: '2026-10-01T00:00:00Z', member_id: 'm1', member_name: 'Jake', event_id: null, event_title: null, event_date: null
  };
  assert.equal(adaptFines([row], [])[0].status, 'Waived');
  assert.equal(adaptFines([{ ...row, status: 'paid' }], [])[0].status, 'Paid');
});
