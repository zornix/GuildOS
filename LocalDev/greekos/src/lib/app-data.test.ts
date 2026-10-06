import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadStartupEvents, loadJobRefresh } from './app-data';
import type { EventDto, EventDetailDto, UpcomingDetailsDto } from '../api';

const event = (id: string): EventDto => ({
  id, title: id, date: '2099-01-01', time: '19:00', location: 'Hall',
  required: false, fine_amount: 0, created_by: 'm1'
} as EventDto);

for (const count of [0, 3]) {
  test(`startup with ${count} upcoming events makes one bulk call`, async () => {
    let bulkCalls = 0;
    let perEventCalls = 0;
    const forbidden = async () => { perEventCalls++; throw new Error('per-event call'); };
    const rows = Array.from({ length: count }, (_, i) => event(`e${i}`));
    const dto: UpcomingDetailsDto = { events: rows.map(detail => ({
      event_id: detail.id, detail: { ...detail, attendance_count: 2 } as EventDetailDto,
      security: [], checkin_link: {}
    })) };
    const calls = {
      getUpcomingEventDetails: async () => { bulkCalls++; return dto; },
      getEvent: forbidden, listSecurity: forbidden, getCheckInLink: forbidden
    };
    const result = await loadStartupEvents(rows, [], calls);
    assert.equal(bulkCalls, 1);
    assert.equal(perEventCalls, 0);
    assert.equal(result.notice, undefined);
    assert.equal(result.events.length, count);
    assert.deepEqual(result.events.map(e => e.checkedInCount), rows.map(() => 2));
  });
}

test('bulk failure keeps list rows and reports a notice without per-event calls', async () => {
  let bulkCalls = 0;
  let perEventCalls = 0;
  const error = new Error('bulk unavailable');
  const forbidden = async () => { perEventCalls++; throw new Error('per-event call'); };
  const calls = {
    getUpcomingEventDetails: async () => { bulkCalls++; throw error; },
    getEvent: forbidden, listSecurity: forbidden, getCheckInLink: forbidden
  };
  const result = await loadStartupEvents([event('e1'), event('e2')], [], calls);
  assert.equal(bulkCalls, 1);
  assert.equal(perEventCalls, 0);
  assert.deepEqual(result.events.map(e => [e.id, e.title]), [['e1', 'e1'], ['e2', 'e2']]);
  assert.equal(result.notice, 'Event details could not be loaded.');
  assert.equal(result.error, error);
});

for (const eventId of [undefined, 'e1']) {
  test(`job refresh reads tasks and ${eventId ? 'the affected event' : 'no event'}`, async () => {
    let taskCalls = 0;
    const eventCalls: string[] = [];
    const detail = event('e1') as EventDetailDto;
    const result = await loadJobRefresh({
      getTasks: async () => { taskCalls++; return []; },
      getEvent: async id => { eventCalls.push(id); return detail; }
    }, eventId);
    assert.equal(taskCalls, 1);
    assert.deepEqual(eventCalls, eventId ? [eventId] : []);
    assert.deepEqual(result.taskRows, []);
    assert.equal(result.detail, eventId ? detail : undefined);
  });
}
