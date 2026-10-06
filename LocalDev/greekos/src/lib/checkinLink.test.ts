import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readCheckinCode, stripCheckinParam } from './checkinLink';

test('readCheckinCode accepts 4-8 alphanumerics and keeps their case (door codes are case-sensitive)', () => {
  assert.equal(readCheckinCode('?checkin=A7x9Kp'), 'A7x9Kp');
  assert.equal(readCheckinCode('?tab=events&checkin=ABCD'), 'ABCD');
  assert.equal(readCheckinCode('?checkin=ABCDEFGH'), 'ABCDEFGH');
});

test('readCheckinCode refuses anything that is not a door code', () => {
  assert.equal(readCheckinCode(''), null);
  assert.equal(readCheckinCode('?tab=events'), null);
  assert.equal(readCheckinCode('?checkin='), null);
  assert.equal(readCheckinCode('?checkin=ABC'), null);
  assert.equal(readCheckinCode('?checkin=ABCDEFGHI'), null);
  assert.equal(readCheckinCode('?checkin=AB%20CD'), null);
  assert.equal(readCheckinCode('?checkin=<script>'), null);
});

test('stripCheckinParam removes only the checkin parameter', () => {
  assert.equal(stripCheckinParam('http://localhost:3000/?checkin=A7x9Kp'), 'http://localhost:3000/');
  assert.equal(stripCheckinParam('http://h/app?tab=events&checkin=ABCD#x'), 'http://h/app?tab=events#x');
  assert.equal(stripCheckinParam('http://h/app?tab=events'), 'http://h/app?tab=events');
});
