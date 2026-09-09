import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney } from './formatters';

test('formatMoney renders integer cents as dollars', () => {
  assert.equal(formatMoney(150), '$1.50');
  assert.equal(formatMoney(123456), '$1,234.56');
  assert.equal(formatMoney(0), '$0.00');
});
