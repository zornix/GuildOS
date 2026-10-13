import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import LoginScreen from './LoginScreen';

test('a reload with a setup-only token opens on the password form with a way back to sign in', () => {
  const html = renderToStaticMarkup(createElement(LoginScreen, { onLoggedIn: () => {}, initialStep: 'password' }));
  assert.match(html, /Choose a password/);
  assert.match(html, /id="new-password"/);
  assert.match(html, /Back to sign in/);
});
