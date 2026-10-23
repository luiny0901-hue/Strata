import test from 'node:test';
import assert from 'node:assert/strict';
import {RequestDeadlines} from './opencode-request-lifecycle.mjs';

function fixture() {
  const timers=new Map();let next=0;const expired=[];
  const pending=new RequestDeadlines({onTimeout:(id,method)=>{expired.push({id,method});pending.close();},
    setTimer:(callback,ms)=>{const id=++next;timers.set(id,{callback,ms});return id;},
    clearTimer:id=>timers.delete(id)});
  return {pending,timers,expired};
}
test('initialize and tool requests have finite separate deadlines',()=>{
  const {pending,timers,expired}=fixture();pending.watch(1,'initialize');pending.watch(2,'tools/call');
  assert.deepEqual([...timers.values()].map(t=>t.ms),[20000,120000]);
  [...timers.values()][1].callback();
  assert.deepEqual(expired,[{id:2,method:'tools/call'}]);
  assert.equal(pending.size,0);assert.equal(timers.size,0);
});
test('ten thousand completed requests leave no timers or retained IDs',()=>{
  const {pending,timers,expired}=fixture();
  for(let id=0;id<10000;id++){pending.watch(id,'tools/call');pending.complete(id);}
  assert.equal(pending.size,0);assert.equal(timers.size,0);assert.equal(expired.length,0);
});
test('late callbacks after completion or close do not fail a new connection',()=>{
  const {pending,timers,expired}=fixture();pending.watch(1,'tools/call');
  const callback=[...timers.values()][0].callback;pending.complete(1);callback();
  pending.watch(1,'tools/call');callback();assert.equal(pending.size,1);
  pending.close();callback();
  assert.equal(expired.length,0);assert.equal(pending.size,0);
});
test('duplicate IDs and excessive outstanding requests are rejected before dispatch',()=>{
  const {pending}=fixture();pending.watch(1,'tools/call');assert.throws(()=>pending.watch(1,'tools/call'));
  assert.equal(pending.atCapacity,false);
  for(let id=2;id<=128;id++)pending.watch(id,'tools/call');
  assert.equal(pending.atCapacity,true);
  assert.throws(()=>pending.watch(129,'tools/call'));
  pending.complete(1);assert.equal(pending.atCapacity,false);pending.watch(129,'tools/call');
  pending.close();assert.equal(pending.size,0);assert.equal(pending.atCapacity,false);
});
