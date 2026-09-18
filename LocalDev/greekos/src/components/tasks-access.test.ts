import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import TasksModule from './TasksModule';
import { can, isOfficerView } from '../lib/session';
import type { Member } from '../types';

const noop = () => {};
const members = [{ id: 'm1', name: 'Ryan Cole' }] as Member[];

function tasks(permissions: string[]) {
  return renderToStaticMarkup(createElement(TasksModule, {
    tasks: [], members, currentMemberName: 'Ryan Cole',
    canCreateTask: can(permissions, 'tasks:create'),
    onAddTask: noop, onToggleTaskStatus: noop, onClaimTask: noop
  }));
}

test('adding a job follows tasks:create', () => {
  assert.equal(isOfficerView(['tasks:create']), false);
  assert.match(tasks(['tasks:create']), /Add job/);
  assert.doesNotMatch(tasks(['standing:view_all']), /Add job/);
});
