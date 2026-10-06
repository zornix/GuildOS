import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import CommandModule from './CommandModule';

test('the command console says what it is: a fixed command list, not natural language', () => {
  const html = renderToStaticMarkup(createElement(CommandModule, {
    members: [], events: [], currentMemberName: 'Test Officer', onExecuteCommand: () => {}
  }));
  assert.doesNotMatch(html, /plain English|natural language|\bAI\b/i);
  assert.match(html, /Type a command\. Supported:/);
  for (const pattern of ['fine NAME $AMOUNT', 'assign TITLE to NAME', 'schedule TITLE on DATE at TIME', 'extend bid to NAME', 'send announcement: TEXT', 'approve excuse for NAME']) {
    assert.ok(html.includes(pattern), `missing pattern ${pattern}`);
  }
});
