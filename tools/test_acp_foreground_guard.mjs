import assert from 'node:assert/strict';
import plugin from '../examples/opencode/acp-foreground-guard/index.js';
let calls = 0;
const make = () => ({name: 'shell', id: 'shell', description: '', execute: async () => {calls++; return {content: 'original'};}});
for (const enabled of ['0', '1']) {
  process.env.OPENCODE_ACP_FOREGROUND_GUARD = enabled;
  const shell = make();
  await plugin.setup({tool: {transform: async callback => callback({list: () => [shell], update: (_, callback) => callback(shell)})}});
  const before = calls;
  const result = await shell.execute({background: true}, {});
  assert.equal(calls - before, enabled === '1' ? 0 : 1);
  if (enabled === '1') assert.equal(result.output.exit, 1);
  for (const input of [{}, {background: false}]) {
    assert.equal((await shell.execute(input, {})).content, 'original');
  }
}
console.log('PASS: disabled guard passes through; enabled guard blocks background only');
