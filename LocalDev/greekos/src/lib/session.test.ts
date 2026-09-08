import { test } from 'node:test';
import assert from 'node:assert/strict';
import { OFFICER_VIEW_KEY, can, isOfficerView } from './session';

test('officer view requires the chapter-wide standing key', () => {
  assert.equal(OFFICER_VIEW_KEY, 'standing:view_all');
  assert.equal(isOfficerView(['standing:view_all', 'tasks:create']), true);
  assert.equal(isOfficerView(['tasks:complete']), false);
  assert.equal(isOfficerView([]), false);
});

test('can() is an exact key match', () => {
  const perms = new Set(['calendar:event:create']);
  assert.equal(can(perms, 'calendar:event:create'), true);
  assert.equal(can(perms, 'calendar:event'), false);
  assert.equal(can([], 'calendar:event:create'), false);
});
