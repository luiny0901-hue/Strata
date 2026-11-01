import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync} from 'node:zlib';
import {targetPixels,typingBudget,reviewedCaptureDimension,approvedForeground} from './foreground-input.mjs';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';

function png(change) {
  const header=Buffer.alloc(13);header.writeUInt32BE(160);header.writeUInt32BE(160,4);header[8]=8;header[9]=6;
  const raw=Buffer.alloc((160*4+1)*160);
  for(let y=0;y<160;y++)for(let x=0;x<160;x++){
    const i=y*641+1+x*4;raw[i]=change?.[0]===x&&change?.[1]===y?200:20;raw[i+3]=255;
  }
  const chunk=(name,data)=>{const b=Buffer.alloc(data.length+12);b.writeUInt32BE(data.length);b.write(name,4);data.copy(b,8);return b;};
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]).toString('base64');
}
test('pointer grounding ignores unrelated pixels but rejects changed target pixels',()=>{
  const args={x:100,y:110};const initial=targetPixels(png(),args,'click');
  assert.equal(targetPixels(png([1,1]),args,'click'),initial);
  assert.notEqual(targetPixels(png([100,110]),args,'click'),initial);
});
test('keyboard grounding checks client area and ignores title-bar activation',()=>{
  const initial=targetPixels(png(),{},'hotkey');
  assert.equal(targetPixels(png([1,1]),{},'hotkey'),initial);
  assert.notEqual(targetPixels(png([100,110]),{},'hotkey'),initial);
});
test('malformed screenshots and missing pointer coordinates are rejected',()=>{
  assert.throws(()=>targetPixels('invalid',{},'click'));
  assert.throws(()=>targetPixels(png(),{},'click'));
});
test('typing lifetime covers deferred Unicode input even with zero requested delay',()=>{
  assert.equal(typingBudget({text:'가'.repeat(181),delay_ms:0}),5430);
  assert.equal(typingBudget({text:'가'.repeat(181),delay_ms:30}),5430);
  assert.equal(typingBudget({text:'abc',delay_ms:50}),150);
  assert.equal(typingBudget({text:'😀'}),30);
  assert.throws(()=>typingBudget({text:'a'.repeat(2001)}));
  assert.throws(()=>typingBudget({text:'abc',delay_ms:-1}));
});

test('foreground recapture preserves reviewed image budget in landscape and portrait',()=>{
  for(const [width,height] of [[1280,720],[1920,1080],[979,986],[720,1280],[2560,1440]])
    assert.equal(reviewedCaptureDimension({width,height}),Math.max(width,height));
  for(const frame of [undefined,{}, {width:0,height:720},{width:1280.5,height:720},{width:Infinity,height:720},{width:7680,height:4320}])
    assert.throws(()=>reviewedCaptureDimension(frame));
});

test('signal-terminated synthetic action rejects without the three-second cleanup delay',async()=>{
  const original=childProcess.spawn;
  let owned;
  childProcess.spawn=()=>{
    owned=original(process.execPath,['-e','process.stdin.resume()'],{stdio:['pipe','pipe','pipe'],windowsHide:true});
    owned.once('spawn',()=>setImmediate(()=>owned.kill('SIGTERM')));
    return owned;
  };
  syncBuiltinESMExports();
  try {
    const start=performance.now();
    await assert.rejects(approvedForeground({driver:'synthetic-only',name:'click',
      args:{pid:123,window_id:456,x:100,y:110},
      frame:{digest:'fixture',time:Date.now(),png:png(),width:160,height:160,bounds:{x:0,y:0,width:160,height:160}},
      captureTools:new Set(),signal:new AbortController().signal,
      confirmHuman:async()=>true}),/exited|pipe/i);
    const elapsed=performance.now()-start;
    assert.equal(owned.signalCode,'SIGTERM');
    assert.ok(elapsed<1500,`already exited synthetic driver took ${elapsed.toFixed(1)} ms`);
  } finally {
    childProcess.spawn=original;
    syncBuiltinESMExports();
    if(owned && owned.exitCode===null && owned.signalCode===null)owned.kill();
  }
});

test('declined or already-cancelled synthetic permission never starts a driver',async()=>{
  const original=childProcess.spawn;
  let starts=0;
  childProcess.spawn=(...args)=>{starts++;return original(...args);};
  syncBuiltinESMExports();
  try {
    for(const cancel of [false,true]) {
      const controller=new AbortController();
      await assert.rejects(approvedForeground({driver:'synthetic-missing-driver',name:'click',
        args:{pid:123,window_id:456,x:100,y:110},
        frame:{digest:'fixture',time:Date.now(),png:png(),width:160,height:160,bounds:{}},
        captureTools:new Set(),signal:controller.signal,
        confirmHuman:async()=>{if(cancel)controller.abort();return cancel;}}),/No input dispatched/);
    }
    assert.equal(starts,0);
  } finally {
    childProcess.spawn=original;
    syncBuiltinESMExports();
  }
});
