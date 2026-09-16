import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleMessages } from './OutboxModule';
import { adaptOutbox } from '../adapters';
import type { OutboxMessageDto } from '../api';

const row = (over: Partial<OutboxMessageDto>): OutboxMessageDto => ({
  id: 'x',
  event_type: 'ANNOUNCEMENT',
  recipient_name: 'Ryan Cole',
  recipient_phone: null,
  body: 'hi',
  status: 'sent',
  attempts: 1,
  created_at: '2026-09-15T00:00:00Z',
  delivered_at: null,
  error: null,
  ...over
});

test('the channel filter keeps only that channel, and "all" keeps everything', () => {
  const messages = adaptOutbox([
    row({ id: 'a', channel: 'email', event_type: 'SETUP_CODE' }),
    row({ id: 'b', channel: 'sms' })
  ]);

  assert.deepEqual(visibleMessages(messages, 'email').map(m => m.id), ['a']);
  assert.deepEqual(visibleMessages(messages, 'sms').map(m => m.id), ['b']);
  assert.deepEqual(visibleMessages(messages, 'all').map(m => m.id), ['a', 'b']);
});

test('a row from a backend with no channel field is an SMS, as it always was', () => {
  assert.equal(adaptOutbox([row({})])[0].channel, 'sms');
});
