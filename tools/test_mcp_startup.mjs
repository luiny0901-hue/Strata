import test from 'node:test';
import assert from 'node:assert/strict';
import {settleMcp} from '../examples/opencode/acp-foreground-guard/mcp-startup.mjs';
test('delayed MCP and debounced registry settle before the first prompt',async()=>{
  let time=0;
  const context={mcp:{list:async()=>({data:[{name:'cua-driver',status:{status:time<300?'pending':'connected'}}]})},tool:{list:async()=>time<400?[{id:'read'}]:[{id:'read'},{id:'cua-driver_click'}]}};
  const result=await settleMcp(context,{expected:()=>['cua-driver'],timeoutMs:2000,now:()=>time,pause:async ms=>{time+=ms;}});
  assert.equal(result.settled,true);assert.equal(result.tools,2);assert.equal(time,600);
});
test('failed/disabled servers do not cause unlimited startup waits',async()=>{
  let time=0;
  const result=await settleMcp({mcp:{list:async()=>({data:[{name:'rea',status:{status:'failed'}}]})},tool:{list:async()=>[]}},
    {expected:()=>['rea'],timeoutMs:2000,now:()=>time,pause:async ms=>{time+=ms;}});
  assert.equal(result.settled,true);assert.equal(time,200);
});
test('missing or permanently pending server reaches a finite limit',async()=>{
  let time=0;
  const result=await settleMcp({mcp:{list:async()=>({data:[]})},tool:{list:async()=>[]}},
    {expected:()=>['rea'],timeoutMs:1000,now:()=>time,pause:async ms=>{time+=ms;}});
  assert.equal(result.settled,false);assert.deepEqual(result.pending,['rea']);assert.equal(time,1000);
});

for(const stage of ['mcp.list','tool.list'])test(`unresponsive ${stage} cannot exceed the initial startup deadline`,async()=>{
  const never=()=>new Promise(()=>{});
  const context={mcp:{list:stage==='mcp.list'?never:async()=>({data:[]})},tool:{list:never}};
  const result=await settleMcp(context,{timeoutMs:25});
  assert.equal(result.settled,false);
  assert.equal(result.stage,stage);
  assert.ok(result.seconds<2,'startup should stop waiting rather than hang');
});
