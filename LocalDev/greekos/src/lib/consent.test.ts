import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  NO_CONSENT,
  NO_EMAIL,
  ROSTER_CSV_HEADER,
  SMS_CONSENT_LABEL,
  outboxFailure
} from './consent';

test('the opt-in label carries every disclosure carriers require', () => {
  for (const required of [
    'GuildOS',
    'chapter announcements',
    'event notices',
    'Message and data rates may apply',
    'Reply STOP to opt out'
  ]) {
    assert.ok(SMS_CONSENT_LABEL.includes(required), `label is missing "${required}"`);
  }
});

test('the opt-in label no longer promises texts that are now emails', () => {
  for (const gone of ['sign-in code', 'dues']) {
    assert.ok(!SMS_CONSENT_LABEL.includes(gone), `label still promises "${gone}" by text`);
  }
});

test('the roster CSV header names the consent column', () => {
  assert.equal(ROSTER_CSV_HEADER, 'name,email,phone,role,consent');
});

test('a no-consent failure is explained and not retryable', () => {
  assert.deepEqual(outboxFailure(NO_CONSENT), {
    text: 'Not sent: member has not opted in to texts.',
    retryable: false
  });
});

test('a missing email address is explained and not retryable', () => {
  assert.deepEqual(outboxFailure(NO_EMAIL), {
    text: 'Not sent: member has no email address.',
    retryable: false
  });
});

test('any other failure keeps the raw error and the retry button', () => {
  assert.deepEqual(outboxFailure('twilio 21610'), {
    text: 'twilio 21610',
    retryable: true
  });
  assert.equal(outboxFailure(undefined).retryable, true);
});
