import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FORBIDDEN_MESSAGE, REFUSED_MESSAGE, UNREACHABLE_MESSAGE, describeError, syncOutcome } from './sync';

test('backend down: the user is told nothing was saved and the optimistic row is rolled back', () => {
  const out = syncOutcome({ backendDown: true, outcome: 'ok', successMessage: 'Created event' });
  assert.equal(out.toast, 'Not saved: the server is unreachable.');
  assert.equal(out.toast, UNREACHABLE_MESSAGE);
  assert.equal(out.rollback, true);
});

test('an API error shows the error message and rolls back', () => {
  const out = syncOutcome({ backendDown: false, outcome: 'error', successMessage: 'Created event', errorMessage: 'Job can no longer be edited' });
  assert.equal(out.toast, 'Job can no longer be edited');
  assert.equal(out.rollback, true);
  assert.equal(syncOutcome({ backendDown: false, outcome: 'error' }).toast, REFUSED_MESSAGE);
});

test('success shows the success message only after the server answered, with no rollback', () => {
  const out = syncOutcome({ backendDown: false, outcome: 'ok', successMessage: 'Created event' });
  assert.equal(out.toast, 'Created event');
  assert.equal(out.rollback, false);
  assert.equal(syncOutcome({ backendDown: false, outcome: 'ok' }).toast, null);
});

test('describeError keeps the permission copy for a 403 and the refusal copy otherwise', () => {
  assert.equal(describeError(Object.assign(new Error('x'), { status: 403 })), FORBIDDEN_MESSAGE);
  assert.equal(describeError(Object.assign(new Error('x'), { status: 409 })), REFUSED_MESSAGE);
  assert.equal(describeError(undefined), REFUSED_MESSAGE);
});
