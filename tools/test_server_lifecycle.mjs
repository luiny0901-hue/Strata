import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import plugin,{restartServer} from '../examples/opencode/server-lifecycle/index.js';

async function fixture(run,mode='ready') {
  const dir=await mkdtemp(path.join(tmpdir(),'strata-restart-'));
  const tokenFile=path.join(dir,'key');await writeFile(tokenFile,'a'.repeat(64));
  const requests=[];
  const server=createServer(async(req,res)=>{
    let raw='';for await(const chunk of req) raw+=chunk;
    const body=JSON.parse(raw);requests.push({path:req.url,body,auth:req.headers.authorization});
    const state=req.url==='/restart'?'starting':mode;
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify({operation_id:body.operation_id,state}));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {await run({controlURL:`http://127.0.0.1:${server.address().port}`,tokenFile},requests);}
  finally {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await rm(dir,{recursive:true,force:true});}
}

test('tool registration is opt-in',async()=>{
  let calls=0;await plugin.setup({tool:{transform:async()=>calls++}});assert.equal(calls,0);
});
test('same tool awaits readiness without a new model prompt',async()=>{
  await fixture(async(options,requests)=>{
    const result=await restartServer({operation_id:'one',checkpoint:'saved; remaining tests'}, {},options);
    assert.match(result.content,/STRATA_RESTART_READY/);
    assert.deepEqual(requests.map(r=>r.path),['/restart','/status']);
    assert.ok(requests.every(r=>r.auth==='Bearer '+'a'.repeat(64)));
    assert.ok(!result.content.includes('a'.repeat(64)));
  });
});
test('failed readiness is a tool error, not completion',async()=>{
  await fixture(async(options)=>{
    // Native OpenCode Tool.Result has no isError field; failures must reject.
    await assert.rejects(restartServer({operation_id:'failed',checkpoint:'saved'}, {},options),/STRATA_RESTART_FAILED/);
  },'failed');
});
test('cancellation notifies owner and never reports ready',async()=>{
  await fixture(async(options,requests)=>{
    const controller=new AbortController();
    const pending=restartServer({operation_id:'cancel',checkpoint:'saved'}, {signal:controller.signal},options);
    setTimeout(()=>controller.abort(),100);
    await assert.rejects(pending,/abort/i);
    assert.equal(requests.at(-1).path,'/cancel');
  },'starting');
});
test('pre-cancelled execution sends no restart',async()=>{
  await fixture(async(options,requests)=>{
    const controller=new AbortController();controller.abort();
    await assert.rejects(restartServer({operation_id:'cancel',checkpoint:'saved'},{signal:controller.signal},options));
    assert.equal(requests.length,0);
  });
});
test('remote control origins are rejected before reading credentials',async()=>{
  await assert.rejects(restartServer({}, {}, {controlURL:'http://external.example:8768',tokenFile:'missing'}),/loopback/);
});
