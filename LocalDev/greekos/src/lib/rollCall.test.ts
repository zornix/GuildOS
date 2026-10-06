import { test } from 'node:test';
import assert from 'node:assert/strict';
import { markRemainingPresent, nextStatus, rollCallSummary } from './rollCall';
import type { Member } from '../types';

const m = (id: string): Member => ({ id, name: id } as Member);
const roster = [m('a'), m('b'), m('c'), m('d')];

test('summary counts each status and the unmarked rest, in roster order', () => {
  const s = rollCallSummary(roster, { b: 'Absent', d: 'Present', zzz: 'Present' });
  assert.equal(s.present, 1);
  assert.equal(s.absent, 1);
  assert.equal(s.unmarked, 2);
  assert.deepEqual(s.marked, [{ memberId: 'b', status: 'Absent' }, { memberId: 'd', status: 'Present' }]);
  assert.equal(s.label, '1 present · 1 absent · 2 unmarked');
});

test('label only names non-zero buckets and says all marked when none left', () => {
  assert.equal(rollCallSummary(roster, {}).label, '4 unmarked');
  const all = rollCallSummary(roster, { a: 'Present', b: 'Late', c: 'Excused', d: 'Present' });
  assert.equal(all.unmarked, 0);
  assert.equal(all.label, '2 present · 1 excused · 1 late');
});

test('markRemainingPresent fills only the gaps', () => {
  const next = markRemainingPresent(roster, { b: 'Absent' });
  assert.deepEqual(next, { a: 'Present', b: 'Absent', c: 'Present', d: 'Present' });
});

const OPTIONS = ['Present', 'Late', 'Excused', 'Absent'] as const;

test('arrow keys move within the row and wrap around', () => {
  assert.equal(nextStatus('Present', 'ArrowRight', OPTIONS), 'Late');
  assert.equal(nextStatus('Late', 'ArrowDown', OPTIONS), 'Excused');
  assert.equal(nextStatus('Absent', 'ArrowRight', OPTIONS), 'Present');
  assert.equal(nextStatus('Late', 'ArrowLeft', OPTIONS), 'Present');
  assert.equal(nextStatus('Present', 'ArrowUp', OPTIONS), 'Absent');
});

test('an unmarked row lands on the first option; other keys do nothing', () => {
  assert.equal(nextStatus(undefined, 'ArrowRight', OPTIONS), 'Present');
  assert.equal(nextStatus(undefined, 'ArrowLeft', OPTIONS), 'Present');
  assert.equal(nextStatus('Late', 'Enter', OPTIONS), null);
  assert.equal(nextStatus('Late', 'a', OPTIONS), null);
});
