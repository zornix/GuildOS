import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import TasksModule from './TasksModule';
import { adaptTasks } from '../adapters';
import type { Member } from '../types';
import type { TaskDto } from '../api';

const members = [{ id: 'm1', name: 'Ryan Cole' }, { id: 'm2', name: 'Alice Park' }] as Member[];

function renderJob(overrides: Partial<TaskDto>, currentMemberName = 'Ryan Cole') {
  const task: TaskDto = {
    id: 'job1', title: 'Set up chairs', description: '', assigned_member_id: null,
    status: 'open', required: false, due_at: null, created_at: '', event_id: 'event1',
    initiative_id: null, kind: 'standard', people_needed: 1, claimants: [], claimed_count: 0,
    ...overrides
  };
  return renderToStaticMarkup(createElement(TasksModule, {
    tasks: adaptTasks([task], members), members, currentMemberName, isOfficer: false,
    onAddTask() {}, onToggleTaskStatus() {}, onClaimTask() {}
  }));
}

test('Jobs shows persisted claimant and hides Claim for that member', () => {
  const html = renderJob({ status: 'in_progress', claimants: ['m1'], claimed_count: 1, people_needed: 2 });
  assert.match(html, /Ryan Cole/);
  assert.match(html, /1\/2 spots filled/);
  assert.doesNotMatch(html, />Claim<\/button>/);
});

test('Jobs offers another member the remaining spot and hides Claim once full', () => {
  const partial = { status: 'in_progress', claimants: ['m1'], claimed_count: 1 };
  assert.match(renderJob({ ...partial, people_needed: 2 }, 'Alice Park'), />Claim<\/button>/);
  assert.doesNotMatch(renderJob(partial, 'Alice Park'), />Claim<\/button>/);
});

test('closed and reported jobs never render a Claim button even if no claimants remain', () => {
  for (const status of ['done_reported', 'approved', 'done', 'cancelled']) {
    assert.doesNotMatch(renderJob({ status }), />Claim<\/button>/, status);
  }
});

test('attached job status is read-only and points to the parent lifecycle', () => {
  for (const parent of [{ event_id: 'event1' }, { event_id: null, initiative_id: 'initiative1' }]) {
    const html = renderJob(parent);
    assert.match(html, /<button[^>]*disabled=""[^>]*title="Report and review this job in its (event|initiative)\."/);
  }
  const standalone = renderJob({ event_id: null });
  assert.doesNotMatch(standalone, /<button[^>]*disabled/);
});
