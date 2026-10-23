import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {TaskApproval} from './opencode-task-approval.mjs';

function fixture() {
  const directory=mkdtempSync(path.join(tmpdir(),'strata-task-test-'));
  const file=path.join(directory,'tasks.json');
  const a={key:'a'.repeat(32),sessionID:'session-a'},b={key:'b'.repeat(32),sessionID:'session-b'};
  const publish=tasks=>writeFileSync(file,JSON.stringify({version:1,owner:process.pid,tasks}));
  publish([a]);const gate=new TaskApproval(file);
  return {a,b,gate,publish,authorize(scope,preview,signal,confirm){gate.confirmInChat=(_task,text,activeSignal)=>confirm(text,activeSignal,'task');return scope.authorize(preview,signal);},close(){gate.close();rmSync(directory,{recursive:true,force:true});}};
}
test('one human approval is reused across actions but never across tasks',async()=>{
  const f=fixture();try {
    let approvals=0;const confirm=async()=>{approvals++;return true;};
    let scope=f.gate.bind('session-a',new AbortController());
    assert.equal(await f.authorize(scope,'first',new AbortController().signal,confirm),true);scope.close();
    scope=f.gate.bind('session-a',new AbortController());
    assert.equal(await f.authorize(scope,'second',new AbortController().signal,confirm),true);scope.close();
    assert.equal(approvals,1);
    f.publish([{...f.a,key:'c'.repeat(32)}]);f.gate.refresh();
    scope=f.gate.bind('session-a',new AbortController());
    assert.equal(await f.authorize(scope,'next request',new AbortController().signal,confirm),true);scope.close();
    assert.equal(approvals,2);
  }finally{f.close();}
});
test('completion/cancellation revokes pending and active foreground input',async()=>{
  const f=fixture();try {
    const controller=new AbortController();const scope=f.gate.bind('session-a',controller);
    await f.authorize(scope,'first',controller.signal,async()=>true);
    f.publish([]);f.gate.refresh();
    assert.equal(controller.signal.aborted,true);assert.equal(f.gate.grants.size,0);
    assert.throws(()=>scope.assertOwned(),/completed or cancelled/);
    assert.throws(()=>f.gate.bind('session-a',new AbortController()),/CUA_TASK_REQUIRED/);
  }finally{f.close();}
});
test('late approval and another session cannot inherit an earlier grant',async()=>{
  const f=fixture();try {
    let accept;const controller=new AbortController();const scope=f.gate.bind('session-a',controller);
    const pending=f.authorize(scope,'first',controller.signal,()=>new Promise(resolve=>accept=resolve));
    f.publish([f.b]);f.gate.refresh();accept(true);
    assert.equal(await pending,false);assert.equal(f.gate.grants.size,0);
    let asked=0;const other=f.gate.bind('session-b',new AbortController());
    assert.equal(await f.authorize(other,'other',new AbortController().signal,async()=>{asked++;return false;}),false);
    assert.equal(await f.authorize(other,'repeat',new AbortController().signal,async()=>{asked++;return true;}),false);
    assert.equal(asked,1);
  }finally{f.close();}
});
test('ambiguous tasks, missing metadata, owner exit and disconnect fail closed',async()=>{
  const f=fixture();try {
    assert.throws(()=>f.gate.bind(undefined,new AbortController()),/CUA_TASK_REQUIRED/);
    f.publish([f.a,{...f.a,key:'d'.repeat(32)}]);
    assert.throws(()=>f.gate.bind('session-a',new AbortController()),/CUA_TASK_REQUIRED/);
    f.publish([f.a]);const c=new AbortController();f.gate.bind('session-a',c);f.gate.close();assert.equal(c.signal.aborted,true);
    f.gate.alive=()=>false;assert.throws(()=>f.gate.bind('session-a',new AbortController()),/CUA_TASK_REQUIRED/);
  }finally{f.close();}
});
