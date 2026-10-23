// Real proxy/Node subprocesses; only an artificial driver runs. No native GUI.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,copyFile,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import readline from 'node:readline';
import {fileURLToPath} from 'node:url';
import {exposedTools} from './opencode-policy.mjs';

async function scenario(mode) {
  const folder=await mkdtemp(path.join(tmpdir(),'cua-offline-'));
  const source=path.dirname(fileURLToPath(import.meta.url));let child;
  try {
    for(const file of ['opencode-task-approval.mjs','opencode-foreground.mjs','opencode-mcp.mjs','opencode-policy.mjs','opencode-catalog.mjs','opencode-grounding.mjs','opencode-request-lifecycle.mjs'])await copyFile(path.join(source,file),path.join(folder,file));
    if(mode==='timeout') {
      // Only the isolated fixture uses a short deadline; production stays 120s.
      const file=path.join(folder,'opencode-request-lifecycle.mjs');
      await writeFile(file,(await readFile(file,'utf8')).replace('120000','40'));
    }
    const tools=[...exposedTools].map(name=>({name,description:name,inputSchema:{type:'object',properties:{}}}));
    await writeFile(path.join(folder,'mcp'),`
const rl=require('readline').createInterface({input:process.stdin});
const actual=!!process.env.CUA_DRIVER_POLICY_FILE;
if(actual)require('fs').writeFileSync('owned-driver.pid',String(process.pid));
const mode=${JSON.stringify(mode)};
if(actual&&mode==='eof')setInterval(()=>{},1000);
rl.on('line',line=>{const m=JSON.parse(line);const send=result=>console.log(JSON.stringify({jsonrpc:'2.0',id:m.id,result}));
if(m.method==='initialize')send({serverInfo:{name:'fixture',version:'1'},capabilities:{tools:{}}});
if(m.method==='tools/list')send({tools:${JSON.stringify(tools)}});
if(m.method==='tools/call'){require('fs').appendFileSync('calls.log','call\\n');if(mode==='exit')process.exit(0);if(mode==='malformed')console.log('not a JSON-RPC response');if(mode==='bad-envelope')console.log('null');if(mode==='eof')send({content:[{type:'text',text:'fixture result'}]});if(mode==='fallback')send({content:[{type:'text',text:'Retry with delivery_mode:foreground'}],structuredContent:{effect:'unverifiable',route:'synthetic_events',delivery:{mode:'background'},escalation:{target:'foreground'}}});}
});
rl.on('close',()=>{if(!actual||mode!=='eof')process.exit(0);});
`);
    child=spawn(process.execPath,[path.join(folder,'opencode-mcp.mjs')],{cwd:folder,env:{...process.env,CUA_DRIVER_EXE:process.execPath,CUA_DRIVER_POLICY_FILE:path.join(folder,'dummy-policy')},stdio:['pipe','pipe','pipe']});
    let stderr='';child.stderr.on('data',data=>stderr+=data);
    const messages=[];const waiters=new Map();
    readline.createInterface({input:child.stdout}).on('line',line=>{const m=JSON.parse(line);messages.push(m);waiters.get(m.id)?.(m);});
    const request=(id,method,params={})=>new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Fixture request timed out: '+stderr)),7000);
      waiters.set(id,message=>{clearTimeout(timer);waiters.delete(id);resolve(message);});
      const message={jsonrpc:'2.0',id,method,params};
      if(id===null) delete message.id;
      child.stdin.write(JSON.stringify(message)+'\n');
    });
    const ended=new Promise(resolve=>child.once('exit',code=>resolve(code)));
    await request(1,'initialize');
    child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');
    const result=await request(mode==='notification'?null:2,'tools/call',mode==='fallback'?{name:'type_text',arguments:{pid:123,window_id:456,text:'fixture',delivery_mode:'background'}}:{name:'list_windows',arguments:{}});
    if(mode==='notification') { assert.equal(result.error.code,-32600);child.stdin.end(); }
    else if(mode==='eof') { assert.equal(result.result.isError,undefined);child.stdin.end(); }
    else if(mode==='fallback') {
      assert.equal(result.result.structuredContent.code,'background_escalation_blocked');
      assert.equal(result.result.structuredContent.escalation,undefined);
      assert.equal(result.result.structuredContent.effect,'unverifiable');
      assert.ok(!JSON.stringify(result).includes('Retry with delivery_mode'));
      child.stdin.end();
    }
    else {
      assert.equal(result.result.isError,true);
      const code=mode==='timeout'?'driver_timeout':['malformed','bad-envelope'].includes(mode)?'driver_protocol_error':'driver_unavailable';
      assert.equal(result.result.structuredContent.code,code);
    }
    const code=await Promise.race([ended,new Promise((_,reject)=>{const t=setTimeout(()=>reject(new Error('Proxy did not terminate')),7000);t.unref();})]);
    assert.equal(code,['eof','notification','fallback'].includes(mode)?0:1,stderr);
    if(mode==='notification') {
      await assert.rejects(readFile(path.join(folder,'calls.log')),error=>error.code==='ENOENT');
    } else assert.equal((await readFile(path.join(folder,'calls.log'),'utf8')).trim().split('\n').length,1);
    const driverPID=Number(await readFile(path.join(folder,'owned-driver.pid'),'utf8'));
    assert.throws(()=>process.kill(driverPID,0),error=>error.code==='ESRCH');
  } finally {
    if(child&&child.exitCode===null)child.kill();
    await rm(folder,{recursive:true,force:true});
  }
}
test('unresponsive driver request fails with uncertainty and no automatic replay',()=>scenario('timeout'));
test('driver exit zero during a request cannot leave a waiter hanging',()=>scenario('exit'));
test('parent EOF closes an uncooperative owned driver within the grace period',()=>scenario('eof'));
test('malformed driver output fails explicitly instead of passing raw bytes to the client',()=>scenario('malformed'));
test('non-object JSON cannot crash or bypass response handling',()=>scenario('bad-envelope'));
test('tool-call notifications without IDs cannot bypass tool policy and dispatch',()=>scenario('notification'));

test('real proxy suppresses forbidden foreground advice and preserves uncertain effects',()=>scenario('fallback'));
