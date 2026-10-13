import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  authErrorMessage,
  isSetupToken,
  normalizeSetupCode,
  stepAfterAuth,
  validateCodeForm,
  validateNewPassword,
  validateSignIn
} from './auth';

test('setup codes forgive case, spaces and dashes', () => {
  assert.equal(normalizeSetupCode(' k7m-2p qr '), 'K7M2PQR');
  assert.equal(normalizeSetupCode('ABCD2345'), 'ABCD2345');
});

test('a grace-login session lands on set-password, a normal one in the app', () => {
  assert.equal(stepAfterAuth({ password_setup_required: true }), 'password');
  assert.equal(stepAfterAuth({}), 'app');
  // redeem-setup-code always sets the flag, so an invite always sets a password.
  assert.equal(stepAfterAuth({ password_setup_required: true }), 'password');
});

test('auth errors read as instructions, not status codes', () => {
  assert.match(authErrorMessage({ status: 403, code: 'PASSWORD_REQUIRED' }, 'x'), /Enter your password/);
  assert.match(authErrorMessage({ status: 429 }, 'x'), /Too many attempts/);
  assert.equal(authErrorMessage({ status: 401, message: 'Invalid credentials' }, 'Wrong email or password.'), 'Wrong email or password.');
  assert.match(authErrorMessage({ status: 0 }, 'x'), /Cannot reach the server/);
  assert.equal(authErrorMessage({ status: 500, message: 'boom' }, 'x'), 'boom');
  assert.equal(authErrorMessage(new Error(''), 'fallback'), 'fallback');
});

test('form validation blocks the obviously-bad submits', () => {
  assert.match(validateSignIn('  ', 'pw') || '', /chapter email/);
  assert.match(validateSignIn('a@b.co', '') || '', /your password/);
  assert.equal(validateSignIn('a@b.co', 'pw'), null);

  assert.match(validateCodeForm('', 'ABCD2345') || '', /email/);
  assert.match(validateCodeForm('a@b.co', 'ABC') || '', /8 characters/);
  assert.equal(validateCodeForm('a@b.co', 'abcd-2345'), null);

  assert.match(validateNewPassword('short', 'short') || '', /8 characters/);
  assert.match(validateNewPassword('longenough', 'longenouhg') || '', /do not match/);
  assert.equal(validateNewPassword('longenough', 'longenough'), null);
});

/** Builds an unsigned JWT-shaped string; only the payload matters to the client. */
function jwt(payload: object): string {
  const b64url = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`;
}

test('a setup-only token is recognised so a reload lands on set-password, not the app', () => {
  assert.equal(isSetupToken(jwt({ sub: 'm1', pwd_setup: true })), true);
});

test('a normal session token is not a setup token', () => {
  assert.equal(isSetupToken(jwt({ sub: 'm1' })), false);
  assert.equal(isSetupToken(jwt({ sub: 'm1', pwd_setup: 'true' })), false);
});

test('a missing or malformed token is not a setup token', () => {
  assert.equal(isSetupToken(null), false);
  assert.equal(isSetupToken(''), false);
  assert.equal(isSetupToken('garbage'), false);
  assert.equal(isSetupToken('a.!!!.c'), false);
});
