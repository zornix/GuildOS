import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWhen } from './parseWhen';

const wed = new Date(2026, 8, 2); // Wednesday 2 Sep 2026

test('weekday, relative and absolute dates resolve to the coming occurrence', () => {
  assert.deepEqual(parseWhen('Friday', '8pm', wed), { date: '2026-09-04', time: '20:00' });
  // On a Friday, "friday" means the next one.
  assert.deepEqual(parseWhen('friday', '8pm', new Date(2026, 8, 4)), { date: '2026-09-11', time: '20:00' });
  assert.deepEqual(parseWhen('tomorrow', 'noon', wed), { date: '2026-09-03', time: '12:00' });
  assert.deepEqual(parseWhen('2026-07-17', '19:00', wed), { date: '2026-07-17', time: '19:00' });
  // A month-day already past means next year.
  assert.deepEqual(parseWhen('July 17', '8:30 pm', wed), { date: '2027-07-17', time: '20:30' });
  assert.deepEqual(parseWhen('October 5', 'midnight', wed), { date: '2026-10-05', time: '00:00' });
});

test('an unreadable date or time refuses instead of guessing', () => {
  assert.equal(parseWhen('blorp', '8pm', wed), null);
  assert.equal(parseWhen('Friday', 'half past beer', wed), null);
  assert.equal(parseWhen('', '', wed), null); // omitted "on"/"at" is not a default
  assert.equal(parseWhen('February 31', '8pm', wed), null);
});
