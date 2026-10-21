import test from 'node:test';
import assert from 'node:assert/strict';
import {WindowGrounding, GroundingError} from './opencode-grounding.mjs';
import {isSafeCall} from './opencode-policy.mjs';

const target = {kind:'window', pid: 4, window_id: 8};
const coords = {target, x: 960, y: 540};
function result(width=1920,height=1080) {
  const png = Buffer.alloc(24);
  Buffer.from([137,80,78,71,13,10,26,10]).copy(png);
  png.writeUInt32BE(width,16); png.writeUInt32BE(height,20);
  return {structuredContent:{window_bounds:{x:2560,y:-100,width:2560,height:1440},capture_id:'capture-1'},content:[{type:'image',mimeType:'image/png',data:png.toString('base64')}]};
}
function capture(g) {
  const r=result();
  g.response(g.request('get_window_state',{pid:4,window_id:8}),r);
  return r;
}
test('valid default window scope is admitted; conflicting identities are rejected',()=>{
  assert.ok(isSafeCall('click',{pid:4,window_id:8,x:10,y:10}));
  assert.equal(isSafeCall('click',{target,pid:5,x:10,y:10}),false);
});
test('screenshot size is explicit; overlay uses screen origin and true image scale exactly once',()=>{
  const g=new WindowGrounding();
  const r=capture(g);
  assert.ok(r.content.at(-1).text.includes('1920x1080'));
  const overlay=g.request('move_cursor',coords).args;
  assert.equal(overlay.x,3840); assert.equal(overlay.y,620);
  assert.equal(g.request('click',coords).args.x,960);
});
test('missing/stale/wrong-window/out-of-bounds/zoom coordinates are rejected before dispatch',()=>{
  let now=0; const g=new WindowGrounding({now:()=>now});
  assert.throws(()=>g.request('click',coords),GroundingError);
  capture(g);
  for(const extra of [{x:1920},{y:-1},{x:NaN},{from_zoom:true},{target:{...target,window_id:9}}]) assert.throws(()=>g.request('click',{...coords,...extra}),GroundingError);
  now=120001;
  assert.throws(()=>g.request('click',coords),GroundingError);
});
test('input consumes grounding; overlapping input and stale in-flight capture are rejected',()=>{
  const g=new WindowGrounding(); capture(g);
  const old=g.request('get_window_state',{pid:4,window_id:8});
  const click=g.request('click',{element_token:'s00000001:3'});
  assert.throws(()=>g.request('click',coords),GroundingError);
  g.response(click,{});
  g.response(old,result());
  assert.throws(()=>g.request('click',coords),GroundingError);
  capture(g);
  assert.ok(g.request('click',coords));
});
test('pixel capture id is attached only to tools whose schema supports it',()=>{
  const g=new WindowGrounding({captureTools:new Set(['click'])});capture(g);
  assert.throws(()=>g.request('click',{...coords,capture_id:'wrong'}),GroundingError);
  assert.equal(g.request('click',coords).args.capture_id,'capture-1');
});
test('fresh element-token calls remain available without an image or extra pointer move',()=>{
  const g=new WindowGrounding();
  assert.ok(g.request('click',{element_token:'s00000001:3'}));
});
test('tree-only/display-only captures cannot authorize pixel input',()=>{
  for(const flags of [{include_screenshot:false},{display_only:true}]) {
    const g=new WindowGrounding();g.response(g.request('get_window_state',{pid:4,window_id:8,...flags}),result());
    assert.throws(()=>g.request('click',coords),GroundingError);
  }
});

test('failed refresh and out-of-order captures never reuse old pixels',()=>{
  const g=new WindowGrounding(); capture(g);
  const older=g.request('get_window_state',{pid:4,window_id:8});
  assert.throws(()=>g.request('click',coords),GroundingError);
  const newer=g.request('get_window_state',{pid:4,window_id:8});
  g.response(newer,{isError:true,content:[]});
  const late=result();g.response(older,late);
  assert.equal(late.isError,true);
  assert.ok(!late.content.some(item=>item.type==='image'));
  assert.throws(()=>g.request('click',coords),GroundingError);
});

test('4K and 8K windows on negative monitor origins map overlay without extra DPI scaling',()=>{
  for(const [width,height] of [[3840,2160],[7680,4320]]) {
    const g=new WindowGrounding();const r=result(1920,1080);
    r.structuredContent.window_bounds={x:-width,y:-200,width,height};
    g.response(g.request('get_window_state',{pid:4,window_id:8}),r);
    const move=g.request('move_cursor',coords).args;
    assert.equal(move.x,-width/2);
    assert.equal(move.y,-200+height/2);
  }
});
