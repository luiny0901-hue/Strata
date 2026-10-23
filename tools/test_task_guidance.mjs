import assert from 'node:assert/strict';
import test from 'node:test';
import plugin,{taskInstruction} from '../examples/opencode/output-recovery/index.js';

async function setup(enabled){
 const tools=[],hooks=[];
 await plugin.setup({options:{taskGuidance:enabled},tool:{transform:async cb=>cb({add:t=>tools.push(t)})},session:{hook:async(name,handler)=>hooks.push({name,handler})}});
 return {tools,hooks};
}
test('conditional policy is opt-in and adds no classifier or guidance tool',async()=>{
 const disabled=await setup(false);assert.ok(!disabled.tools.some(t=>t.name==='strata_writing_guidance'));
 const {tools,hooks}=await setup(true);assert.deepEqual(tools.map(t=>t.name),disabled.tools.map(t=>t.name));
 const event={system:[],tools:{}};const hook=hooks.find(h=>h.name==='context').handler;
 for(let i=0;i<10;i++)await hook(event);
 assert.equal(event.system.filter(p=>p.text===taskInstruction).length,1);
 assert.ok(taskInstruction.length<700);
 const ordinary={system:[],tools:{}};await disabled.hooks.find(h=>h.name==='context').handler(ordinary);
 assert.ok(!ordinary.system.some(p=>p.text===taskInstruction));
});
test('canonical routing replaces only owned fallback and preserves other policies',async()=>{
 const {hooks}=await setup(true);const hook=hooks.find(h=>h.name==='context').handler;
 const event={system:[{type:'text',text:taskInstruction},{type:'text',text:'external'},{type:'text',text:'<!-- strata-task-routing:v1 --> canonical'}],tools:{}};
 await hook(event);assert.ok(!event.system.some(p=>p.text===taskInstruction));assert.ok(event.system.some(p=>p.text==='external'));
});
test('checkpoint preserves prose only conditionally and never grants implementation',async()=>{
 const {hooks}=await setup(true);const event={system:[]};const hook=hooks.find(h=>h.name==='compaction').handler;
 await hook(event);await hook(event);assert.equal(event.system.length,1);
 assert.match(event.system[0].text,/Only for active prose work/);assert.match(event.system[0].text,/last saved position/);
 assert.match(event.system[0].text,/Do not turn fiction into implementation authority/);
 for(const text of ['인물 이름·관계','시점·문체','미회수 복선','16000자','질문·부정·인용','요청 범위 밖'])assert.ok(taskInstruction.includes(text));
});
