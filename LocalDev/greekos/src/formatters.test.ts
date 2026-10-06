import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney, hasStarted, isoDay, isWithin36Hours, monthCells } from './formatters';

test('formatMoney renders integer cents as dollars', () => {
  assert.equal(formatMoney(150), '$1.50');
  assert.equal(formatMoney(123456), '$1,234.56');
  assert.equal(formatMoney(0), '$0.00');
});

test('isoDay is the local calendar day', () => {
  assert.equal(isoDay(new Date(2026, 6, 4)), '2026-07-04');
});

test('monthCells pads to the weekday of the 1st and handles leap years', () => {
  const july2026 = monthCells(2026, 6); // July 1 2026 is a Wednesday -> 3 blanks
  assert.equal(july2026.length, 3 + 31);
  assert.equal(july2026[0], null);
  assert.equal(july2026[3], '2026-07-01');
  assert.equal(july2026[33], '2026-07-31');
  assert.equal(monthCells(2024, 1).filter(Boolean).length, 29);
});

test('the T-36h unclaim lock and hasStarted follow the event start', () => {
  const start = new Date('2026-07-13T18:00').getTime();
  const hours = (n: number) => n * 60 * 60 * 1000;
  assert.equal(isWithin36Hours('2026-07-13', '18:00', start - hours(40)), false);
  assert.equal(isWithin36Hours('2026-07-13', '18:00', start - hours(10)), true);
  assert.equal(isWithin36Hours('2026-07-13', '18:00', start + hours(2)), true); // started: stays locked
  assert.equal(hasStarted('2026-07-13', '18:00', start - hours(10)), false);
  assert.equal(hasStarted('2026-07-13', '18:00', start + hours(2)), true);
});
