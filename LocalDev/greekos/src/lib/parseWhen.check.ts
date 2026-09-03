// run: npx tsx src/lib/parseWhen.check.ts   (exits non-zero on failure)
import assert from 'node:assert';
import { parseWhen } from './parseWhen';

const wed = new Date(2026, 8, 2); // Wednesday 2 Sep 2026

assert.deepEqual(parseWhen('Friday', '8pm', wed), { date: '2026-09-04', time: '20:00' });
assert.deepEqual(parseWhen('friday', '8pm', new Date(2026, 8, 4)), { date: '2026-09-11', time: '20:00' }); // on a Friday: the next one
assert.deepEqual(parseWhen('tomorrow', 'noon', wed), { date: '2026-09-03', time: '12:00' });
assert.deepEqual(parseWhen('2026-07-17', '19:00', wed), { date: '2026-07-17', time: '19:00' });
assert.deepEqual(parseWhen('July 17', '8:30 pm', wed), { date: '2027-07-17', time: '20:30' }); // already past -> next year
assert.deepEqual(parseWhen('October 5', 'midnight', wed), { date: '2026-10-05', time: '00:00' });
assert.equal(parseWhen('blorp', '8pm', wed), null);
assert.equal(parseWhen('Friday', 'half past beer', wed), null);
assert.equal(parseWhen('', '', wed), null);          // omitted "on"/"at" is not a default
assert.equal(parseWhen('February 31', '8pm', wed), null);

console.log('parseWhen check OK');
