import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Sidebar from './Sidebar';
import AppShell from './layout/AppShell';

const noop = () => {};

function sidebar(permissions: string[]) {
  return renderToStaticMarkup(createElement(Sidebar, {
    activeTab: 'dashboard', setActiveTab: noop, permissions: new Set(permissions),
    currentMemberName: 'Test Brother', onLogout: noop, open: true, onClose: noop
  }));
}

function shell(permissions: string[]) {
  return renderToStaticMarkup(createElement(AppShell, {
    activeTab: 'dashboard', setActiveTab: noop, permissions: new Set(permissions),
    currentMemberName: 'Test Brother', onLogout: noop, toastMessage: null, onDismissToast: noop,
    loading: false, backendDown: false, children: null
  }));
}

test('the Officer label is the standing:view_all presentation, derived from the permission set', () => {
  assert.match(sidebar(['standing:view_all']), />Officer</);
  assert.doesNotMatch(sidebar(['tasks:create']), />Officer</);
  assert.match(sidebar(['tasks:create']), />Member</);
  assert.match(shell(['standing:view_all']), />Officer</);
  assert.match(shell([]), />Member</);
});
