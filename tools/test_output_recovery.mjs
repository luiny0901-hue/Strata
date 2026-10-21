import test from 'node:test';
import assert from 'node:assert/strict';
import {recoverStream} from '../examples/opencode/output-recovery/index.js';
import plugin from '../examples/opencode/output-recovery/index.js';
import {intentInstruction} from '../examples/opencode/output-recovery/index.js';
import {instruction} from '../examples/opencode/output-recovery/index.js';

test('coding guidance scales short changes without turning call size into file architecture', async () => {
  const hooks=[];
  await plugin.setup({tool:{transform:async()=>{}},session:{hook:async(name,handler)=>hooks.push({name,handler})}});
  const event={system:[],tools:{write:{description:'write',input:{properties:{content:{type:'string',maxLength:8000}}}}}};
  await hooks.find(item=>item.name==='context').handler(event);
  assert.ok(event.system.some(item=>item.text===instruction));
  assert.ok(instruction.includes('별도 계획 문서·인계 파일·새 추상화·파일 분할을 만들지 않는다'));
  assert.ok(instruction.includes('최종 파일 크기나 모듈 분할 기준이 아니다'));
  assert.equal(event.tools.write.input.properties.content.maxLength,8000);
});

test('each model context receives intent boundary, including after compaction', async () => {
  const hooks=[];
  await plugin.setup({tool:{transform:async()=>{}}, session:{hook:async(name,handler)=>hooks.push({name,handler})}});
  const hook=hooks.find(item=>item.name==='context');
  for (let turn=0;turn<3;turn++) {
    const event={system:[],tools:{}};
    await hook.handler(event);
    assert.equal(event.system.filter(item=>item.text===intentInstruction).length,1);
  }
  for (const term of ['부정·조건·인용', '읽기 전용', '응/그래/좋아', '확인하고 문제 있으면 고쳐줘', '압축·재연결']) assert.ok(intentInstruction.includes(term));
  const registered={system:[{type:'text',text:'<!-- strata-intent-policy:v2 --> canonical user policy'}],tools:{}};
  await hook.handler(registered);
  assert.equal(registered.system.filter(item=>item.text===intentInstruction).length,0);
});

test('reusing a context object does not accumulate instructions or schema descriptions', async () => {
  const hooks=[];
  await plugin.setup({tool:{transform:async()=>{}},session:{hook:async(name,handler)=>hooks.push({name,handler})}});
  const event={system:[],tools:{write:{description:'write',input:{properties:{content:{type:'string'}}}}}};
  const context=hooks.find(item=>item.name==='context').handler;
  await context(event);
  const original=JSON.stringify(event);
  for(let i=0;i<10;i++) await context(event);
  assert.equal(JSON.stringify(event),original);
});

test('checkpoint guidance is installed without ACP and remains scoped to configured provider', async () => {
  const hooks = [];
  await plugin.setup({options:{providerID:'test'}, tool:{transform:async()=>{}}, session:{hook:async(name, handler, options)=>hooks.push({name, handler, options})}});
  const hook = hooks.find(item=>item.name==='compaction');
  assert.equal(hook.options.providerID, 'test');
  const event = {system:[{type:'text',text:'<!-- strata-summary-basic:v1 --> ACP fallback'}, {type:'text',text:'preserve third-party policy'}]};
  await hook.handler(event);
  assert.ok(!event.system.some(item=>item.text.startsWith('<!-- strata-summary-basic:v1 -->')));
  assert.ok(event.system.some(item=>item.text==='preserve third-party policy'));
  const text = event.system.map(item=>item.text).join('\n');
  assert.match(text, /partially written file/);
  assert.match(text, /re-read only the relevant current ranges\/diff/);
  assert.match(text, /required English summary headings/);
  assert.match(text, /question, read-only inspection, design, or implementation/);
  assert.match(text, /historical TODOs do not grant new execution permission/);
  assert.match(text, /Compaction alone does not invalidate a passed check/);
  assert.match(text, /changes do invalidate it/);
  assert.match(text, /replay uncertain side effects/);
  assert.match(text, /canonical design paths/);
  assert.match(text, /Do not invent ownership/);
});

const packet = (delta, finish_reason = null) => 'data: ' + JSON.stringify({choices: [{index: 0, delta, finish_reason}]}) + '\r\n\r\n';
const tool = {tool_calls: [{index: 0, id: 'original', type: 'function', function: {name: 'write', arguments: '{"content":"한글'}}]};
async function stream(text, attempt = 1) {
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream({start(c) {for (let i = 0; i < bytes.length; i += 7) c.enqueue(bytes.slice(i, i + 7)); c.close();}});
  return new Response(recoverStream(body, () => attempt, () => {})).text();
}
test('truncated tool arguments are discarded and replaced with recovery, across UTF8/SSE boundaries', async () => {
  const text = await stream(packet(tool) + packet({}, 'length') + 'data: [DONE]\r\n\r\n');
  assert.ok(text.includes('strata_output_recovery'));
  assert.ok(!text.includes('original'));
  assert.ok(text.includes('tool_calls'));
});
test('confirmed normal tools retain original arguments and finish reason', async () => {
  const valid = {tool_calls: [{index: 0, id: 'original', type: 'function', function: {name: 'write', arguments: '{"content":"한글"}'}}]};
  const text = await stream(packet(valid) + packet({}, 'tool_calls') + 'data: [DONE]\n\n');
  assert.ok(text.includes('original'));
  assert.ok(text.includes('한글'));
  assert.ok(!text.includes('strata_output_recovery'));
});
test('third consecutive truncation does not schedule another retry or emit partial tool', async () => {
  const text = await stream(packet(tool) + packet({}, 'length') + 'data: [DONE]\n\n', 3);
  assert.ok(text.includes('length'));
  assert.ok(!text.includes('strata_output_recovery'));
  assert.ok(!text.includes('original'));
});
test('text responses pass through without a recovery call', async () => {
  const text = await stream(packet({content: 'answer'}) + packet({}, 'stop') + 'data: [DONE]\n\n');
  assert.ok(text.includes('answer'));
  assert.ok(!text.includes('strata_output_recovery'));
});
test('disconnected incomplete tool never reaches execution as a confirmed call', async () => {
  await assert.rejects(stream(packet(tool)), /without confirmation/);
});
test('malformed arguments at normal finish cannot be heuristically repaired and executed', async () => {
  const text = await stream(packet(tool) + packet({}, 'tool_calls') + 'data: [DONE]\n\n');
  assert.ok(text.includes('invalid_json'));
  assert.ok(text.includes('strata_output_recovery'));
  assert.ok(!text.includes('original'));
});
test('refusal stays a refusal without recovery or partial tool execution', async () => {
  const text = await stream(packet(tool) + packet({}, 'content_filter') + 'data: [DONE]\n\n');
  assert.ok(text.includes('content_filter'));
  assert.ok(!text.includes('strata_output_recovery'));
  assert.ok(!text.includes('original'));
});
test('repeated malformed JSON fails instead of reporting successful completion', async () => {
  await assert.rejects(stream(packet(tool) + packet({}, 'tool_calls') + 'data: [DONE]\n\n', 3), /budget exhausted/);
});

test('SSE keepalive between tool fragments does not abort valid work', async () => {
  const tail = {tool_calls:[{index:0,function:{arguments:'"}'}}]};
  const text = await stream(packet(tool) + ': keepalive\n\n' + packet(tail) + packet({},'tool_calls') + 'data: [DONE]\n\n');
  assert.ok(text.includes('original'));
  assert.ok(!text.includes('strata_output_recovery'));
});

test('truncated text or premature DONE cannot masquerade as normal completion', async () => {
  await assert.rejects(stream(packet({content:'work in progress'})), /without confirmation/);
  await assert.rejects(stream(packet({content:'work in progress'})+'data: [DONE]\n\n'), /missing finish_reason/);
});

test('malformed SSE JSON is not passed to downstream argument repair', async () => {
  await assert.rejects(stream('data: {"choices":broken}\n\n'), /Malformed SSE JSON/);
});

test('interleaved tools preserve IDs and arguments after shallow packet buffering', async () => {
  const first={tool_calls:[0,1].map(index=>({index,id:`call_${index}`,type:'function',function:{name:'write',arguments:'{"content":"'}}))};
  const middle={tool_calls:[{index:1,function:{arguments:'second'}},{index:0,function:{arguments:'first'}}]};
  const tail={tool_calls:[0,1].map(index=>({index,function:{arguments:'"}'}}))};
  const output=await stream(packet(first)+packet(middle)+packet(tail)+packet({},'tool_calls')+'data: [DONE]\n\n');
  const argumentsByIndex=new Map();
  for(const raw of output.split('\n\n')) {
    if(!raw.startsWith('data: {')) continue;
    for(const call of JSON.parse(raw.slice(6)).choices[0].delta.tool_calls ?? []) {
      argumentsByIndex.set(call.index,(argumentsByIndex.get(call.index)??'')+(call.function?.arguments??''));
    }
  }
  assert.deepEqual(JSON.parse(argumentsByIndex.get(0)),{content:'first'});
  assert.deepEqual(JSON.parse(argumentsByIndex.get(1)),{content:'second'});
  assert.ok(output.includes('call_0') && output.includes('call_1'));
});

test('consumer cancellation reaches upstream without recovering or confirming partial tools', async () => {
  let cancelled=false,retries=0,completed=0,first=true;
  const body=new ReadableStream({pull(c){if(first){first=false;c.enqueue(new TextEncoder().encode(packet(tool)));}},cancel(){cancelled=true;}});
  const reader=recoverStream(body,()=>++retries,()=>completed++).getReader();
  await reader.read();
  await reader.cancel('user stopped');
  for(let i=0;i<10&&!cancelled;i++) await new Promise(resolve=>setTimeout(resolve,1));
  assert.equal(cancelled,true);
  assert.equal(retries,0);
  assert.equal(completed,0);
});
