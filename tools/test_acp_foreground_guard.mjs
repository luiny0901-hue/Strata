import assert from 'node:assert/strict';
import plugin from '../examples/opencode/acp-foreground-guard/index.js';
let calls = 0;
delete process.env.OPENCODE_ACP_TURN_GUARD;
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
{
  let received;
  const shell = {...make(), execute:async input=>{received=input; return {};}};
  await plugin.setup({tool:{transform:async callback=>callback({list:()=>[shell],update:(_,callback)=>callback(shell)})}});
  await shell.execute({timeout:0}, {});
  assert.equal(received.timeout,120000);
  await shell.execute({timeout:420000}, {});
  assert.equal(received.timeout,420000);
  await shell.execute({}, {});
  assert.equal(received.timeout,undefined);
}
console.log('PASS: explicit unlimited shell wait becomes finite; task-specific deadlines preserved');
{
  let dispatched=0;
  const tools=['shell','subagent'].map(name=>({name,id:name,description:'',execute:async()=>{dispatched++;}}));
  await plugin.setup({tool:{transform:async callback=>callback({list:()=>tools,update:(id,callback)=>callback(tools.find(tool=>tool.id===id))})}});
  const controller=new AbortController();controller.abort();
  for(const tool of tools) await assert.rejects(tool.execute({background:false},{signal:controller.signal}),error=>error.name==='AbortError');
  assert.equal(dispatched,0);
}
console.log('PASS: already cancelled requests cannot dispatch queued shell or subagent');

process.env.OPENCODE_ACP_TURN_GUARD = '1';
const hooks = new Map();
let idle = null;
let childInput;
const subagent = {name:'subagent',id:'subagent',description:'',execute:async input=>{childInput=input;return {content:'child result'};}};
await plugin.setup({
  tool:{transform:async callback=>callback({list:()=>[subagent],update:(_,callback)=>callback(subagent)})},
  session:{hook:async(name,callback)=>{hooks.set(name,callback);},get:async()=>({time:{idle}})},
});
await subagent.execute({background:true,prompt:'child'},{});
assert.equal(childInput.background,false);
const primary={sessionID:'session-one',kind:'primary'};
await assert.rejects(hooks.get('model.request')(primary),/ACP_OUT_OF_TURN_BLOCKED/);
await hooks.get('model.request')({...primary,kind:'compaction'});
hooks.get('prompt')({sessionID:primary.sessionID});
await hooks.get('model.request')(primary);
await hooks.get('model.request')(primary);
idle='2026-10-21T10:00:00Z';
await assert.rejects(hooks.get('model.request')(primary),/already ended/);
hooks.get('prompt')({sessionID:primary.sessionID});
await hooks.get('model.request')(primary);
console.log('PASS: subagents awaited; unowned/late inference blocked; compaction and user follow-up allowed');
for (const [attempt, delay, permitted] of [[2,2000,true],[4,10000,true],[5,2000,false],[2,60000,false]]) {
  const event={attempt,decision:{retry:true,delay}};
  hooks.get('retry')(event);
  assert.equal(event.decision.retry,permitted);
}
const permanent={attempt:2,decision:{retry:false}};
hooks.get('retry')(permanent);
assert.equal(permanent.decision.retry,false);
console.log('PASS: transient retries bounded without overriding permanent errors or Retry-After');
