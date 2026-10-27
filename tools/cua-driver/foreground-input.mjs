import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname, basename } from 'node:path';
import readline from 'node:readline';
import { createHash } from 'node:crypto';
import { inflateSync } from 'node:zlib';

export const foregroundTool = {
  name: 'approved_foreground_action',
  description: 'Only when background input is confirmed ineffective: use CUA foreground input on an exact observed window. A client with request-scoped approval may reuse the human approval until that request completes, is cancelled or disconnects. Other clients require approval for each action. Approval cannot be supplied by the model. Never automate the approval dialog. No desktop, UAC or shell input. Inspect results. No automatic retries.',
  inputSchema: {type:'object', additionalProperties:false, required:['action','arguments'], properties:{
    action:{type:'string',enum:['click','double_click','right_click','drag','scroll','type_text','press_key','hotkey']},
    arguments:{type:'object',description:'Native CUA action arguments, explicit pid and window_id required. Screenshot-local coordinates only; no target, element_token, scope or delivery_mode. The proxy supplies foreground and the fresh capture ID.'},
  }},
};
const allowed = new Set(foregroundTool.inputSchema.properties.action.enum);
const digest = result => {
  const picture = result?.content?.find(item => item.type === 'image' && item.mimeType === 'image/png');
  return picture ? createHash('sha256').update(picture.data).digest('hex') : undefined;
};
export { digest as screenshotDigest };

export function reviewedCaptureDimension(frame) {
  if(!Number.isInteger(frame?.width)||!Number.isInteger(frame?.height)||frame.width<=0||frame.height<=0
      ||frame.width*frame.height>16777216)
    throw new Error('Screenshot dimensions are unavailable or unsupported; inspect a fresh target window.');
  return Math.max(frame.width,frame.height);
}

export function typingBudget(args) {
  if(typeof args.text!=='string')throw new Error('type_text requires text.');
  const delay=args.delay_ms??30;
  if(!Number.isInteger(delay)||delay<0||delay>200)throw new Error('Invalid character delay.');
  // Native foreground delivery can return while its asynchronous key stream is
  // still running. Keep its owner alive for the advertised delivery interval.
  const milliseconds=Array.from(args.text).length*Math.max(30,delay);
  if(milliseconds>60000)throw new Error('Foreground text exceeds the one-minute delivery budget. Use file tools or smaller, verified input.');
  return milliseconds;
}

async function settleTyping(milliseconds,signal) {
  if(milliseconds<=0)return;
  signal.throwIfAborted();
  await new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);reject(new Error('Typing cancelled; input may be partial. Inspect the window before recovery.'));};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},milliseconds);
    signal.addEventListener('abort',abort,{once:true});
  });
}

// Compare the reviewed target pixels rather than PNG encodings or title-bar
// activation colors. Unsupported PNG formats fail closed.
export function targetPixels(data,args,name) {
  const png=Buffer.from(data,'base64');
  if(!png.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) throw new Error('Unsupported screenshot');
  const width=png.readUInt32BE(16),height=png.readUInt32BE(20),type=png[25];
  const channels=type===6?4:type===2?3:0;
  if(png[24]!==8 || png[28]!==0 || !channels || width*height>16777216) throw new Error('Unsupported screenshot format');
  const chunks=[];
  for(let at=8;at+12<=png.length;){const size=png.readUInt32BE(at);if(at+size+12>png.length)throw new Error('Invalid screenshot');if(png.toString('ascii',at+4,at+8)==='IDAT')chunks.push(png.subarray(at+8,at+8+size));at+=size+12;}
  const stride=width*channels, raw=inflateSync(Buffer.concat(chunks),{maxOutputLength:(stride+1)*height});
  if(raw.length!==(stride+1)*height)throw new Error('Invalid screenshot data');
  const pixels=Buffer.alloc(stride*height);
  const paeth=(a,b,c)=>{const p=a+b-c,aa=Math.abs(p-a),bb=Math.abs(p-b),cc=Math.abs(p-c);return aa<=bb&&aa<=cc?a:bb<=cc?b:c;};
  for(let y=0;y<height;y++){
    const filter=raw[y*(stride+1)];if(filter>4)throw new Error('Invalid screenshot filter');
    for(let x=0;x<stride;x++){
      const i=y*stride+x,a=x>=channels?pixels[i-channels]:0,b=y?pixels[i-stride]:0,c=y&&x>=channels?pixels[i-stride-channels]:0;
      pixels[i]=(raw[y*(stride+1)+1+x]+(filter===0?0:filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):paeth(a,b,c)))&255;
    }
  }
  const points=name==='drag'?[[args.from_x,args.from_y],[args.to_x,args.to_y]]:[[args.x,args.y]];
  const bounded=points.every(([x,y])=>Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&y>=0&&x<width&&y<height);
  if(!bounded && ['click','double_click','right_click','drag','scroll'].includes(name))throw new Error('Foreground pointer input requires screenshot coordinates.');
  const regions=bounded?points.map(([x,y])=>[Math.max(0,Math.floor(x)-40),Math.max(0,Math.floor(y)-40),Math.min(width,Math.floor(x)+41),Math.min(height,Math.floor(y)+41)]):[[0,Math.min(60,height),width,Math.max(Math.min(60,height),height-24)]];
  const hash=createHash('sha256').update(`${width}:${height}:${channels}`);
  for(const [left,top,right,bottom]of regions)for(let y=top;y<bottom;y++)hash.update(pixels.subarray(y*stride+left*channels,y*stride+right*channels));
  return hash.digest('hex');
}

function run(exe, args, env, signal, timeout=65000) {
  return new Promise((resolve,reject) => {
    // This child presents the human consent UI. Hiding its initial window can
    // also hide the first WinForms dialog on Windows.
    const child=spawn(exe,args,{env,windowsHide:false,stdio:['ignore','pipe','pipe'],signal});
    let output='';
    let diagnostic='';
    const timer=setTimeout(()=>child.kill(),timeout);
    child.stdout.on('data',data=>{ if(output.length<4096) output+=data; });
    child.stderr.on('data',data=>{if(diagnostic.length<2048) diagnostic+=data;});
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.on('exit',code=>{clearTimeout(timer);if(code!==0 && !signal.aborted) reject(new Error(`Approval UI unavailable (exit ${code}): ${diagnostic.slice(0,2048)}`));else resolve(output.trim());});
  });
}

async function confirm(preview,signal,scope='once') {
  if(process.platform==='win32') {
    // Fixed code, with data transported separately. No model-authored shell script.
    const script=`Add-Type -AssemblyName System.Windows.Forms
$form=New-Object System.Windows.Forms.Form
$form.Text=$env:STRATA_CUA_APPROVAL_TITLE; $form.Width=640; $form.Height=420; $form.TopMost=$true; $form.StartPosition='CenterScreen'
$label=New-Object System.Windows.Forms.TextBox
$label.Multiline=$true; $label.ReadOnly=$true; $label.ScrollBars='Vertical'; $label.SetBounds(15,15,590,290)
$label.Text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:STRATA_CUA_APPROVAL_PREVIEW)); $form.Controls.Add($label)
$yes=New-Object System.Windows.Forms.Button; $yes.Text=$env:STRATA_CUA_APPROVAL_BUTTON; $yes.SetBounds(310,320,140,35); $yes.DialogResult='Yes'; $form.Controls.Add($yes)
$no=New-Object System.Windows.Forms.Button; $no.Text='취소'; $no.SetBounds(465,320,140,35); $no.DialogResult='Cancel'; $form.Controls.Add($no)
$form.AcceptButton=$no; $form.CancelButton=$no
$form.Add_Shown({$form.Activate();$form.BringToFront()})
$timer=New-Object System.Windows.Forms.Timer; $timer.Interval=60000; $timer.Add_Tick({$form.Close()}); $timer.Start()
try {if($form.ShowDialog() -eq 'Yes'){[Console]::Write('ALLOW')}} finally {$timer.Stop();$timer.Dispose();$form.Dispose()}`;
    const exe=join(process.env.SystemRoot??'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
    return await run(exe,['-NoProfile','-STA','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],
      {...process.env,STRATA_CUA_APPROVAL_PREVIEW:Buffer.from(preview).toString('base64'),STRATA_CUA_APPROVAL_TITLE:scope==='task'?'CUA 현재 작업 전체 승인':'CUA 전경 입력 승인 (1회)',STRATA_CUA_APPROVAL_BUTTON:scope==='task'?'작업 완료까지 허용':'동작 1회 허용'},signal)==='ALLOW';
  }
  if(process.platform==='darwin') {
    const script='on run argv\nset r to display dialog (item 1 of argv) with title (item 2 of argv) buttons {"취소", "허용"} default button "취소" cancel button "취소" giving up after 60\nif not gave up of r and button returned of r is "허용" then return "ALLOW"\nend run';
    return await run('/usr/bin/osascript',['-e',script,preview,scope==='task'?'CUA 현재 작업 전체 승인':'CUA 전경 입력 승인 (1회)'],process.env,signal)==='ALLOW';
  }
  return false;
}

export async function approvedForeground({driver,name,args,frame,captureTools,signal,authorize,confirmHuman=confirm,assertOwned=()=>{}}) {
  if(!allowed.has(name) || !args || typeof args!=='object' || Array.isArray(args)
    || !Number.isInteger(args.pid) || args.pid<=0 || !Number.isInteger(args.window_id) || args.window_id<=0
    || ['target','element_token','scope','delivery_mode','from_zoom'].some(key=>args[key]!==undefined))
    throw new Error('Exact pid/window_id and a supported single action are required; tokens and desktop targets are not accepted.');
  if(!frame?.digest || Date.now()-frame.time>120000) throw new Error('Inspect a fresh screenshot of this exact window before requesting approval.');
  const captureDimension=reviewedCaptureDimension(frame);
  const frozen=structuredClone(args);
  const deliveryBudget=name==='type_text'?typingBudget(frozen):0;
  if(!frame.png) throw new Error('Inspect the latest window screenshot before approval.');
  const expectedPixels=targetPixels(frame.png,frozen,name);
  const preview=`이 동작은 사용자의 마우스·키보드와 포커스를 방해할 수 있습니다.\r\n${authorize?"아래 내용은 현재 작업의 첫 동작입니다. 작업 전체 승인 범위는 상단 설명을 확인하세요.":"승인 범위: 아래 창에서 아래 동작 한 번."} 채팅 승인 대기는 최대 120초 후 종료됩니다.\r\nPID=${args.pid}, 창 ID=${args.window_id}\r\n동작=${name}\r\n${JSON.stringify(frozen,null,2)}\r\n\r\n보안 데스크톱/UAC에는 사용할 수 없습니다.`;
  if(preview.length>16000) throw new Error('Action is too large to review. Use file tools for long content.');
  if(!(authorize?await authorize(preview,signal,confirmHuman):await confirmHuman(preview,signal)) || signal.aborted) throw new Error('Foreground permission declined, cancelled, expired or unavailable. No input dispatched.');
  assertOwned();
  let child, lines, directory;
  const waiters=new Map();
  let serial=0;
  const fail=error=>{for(const w of waiters.values()){clearTimeout(w.timer);w.reject(error);}waiters.clear();};
  try {
    directory=await mkdtemp(join(tmpdir(),'strata-cua-approved-'));
    const policy=join(directory,'once.rego');
    // A separate process: the normal background process never receives a foreground policy.
    // Only the reviewed tool and exact window can pass this short-lived native policy.
    const approved={...frozen,delivery_mode:'foreground'};
    await writeFile(policy,`package cua.policy\nimport rego.v1\ndefault allow := false\nallow if { input.tool == "get_window_state"; input.arguments.pid == ${args.pid}; input.arguments.window_id == ${args.window_id} }\nallow if { input.tool == ${JSON.stringify(name)}; input.arguments.pid == ${args.pid}; input.arguments.window_id == ${args.window_id}; input.arguments.delivery_mode == "foreground" }\n`);
    if(signal.aborted) throw new Error('Cancelled before dispatch.');
    child=spawn(driver,['mcp'],{windowsHide:true,stdio:['pipe','pipe','inherit'],signal,
      env:{...process.env,CUA_DRIVER_POLICY_FILE:policy,CUA_DRIVER_MANAGED_POLICY_FILE:policy,CUA_DRIVER_PERMISSION_MODE:'standard'}});
    lines=readline.createInterface({input:child.stdout});
    child.on('error',fail);child.stdin.on('error',fail);
    child.on('exit',()=>fail(new Error('Approved driver exited; do not replay input.')));
    lines.on('line',line=>{try {const msg=JSON.parse(line);const w=waiters.get(msg.id);if(w){waiters.delete(msg.id);clearTimeout(w.timer);msg.error?w.reject(new Error('Driver rejected request')):w.resolve(msg.result);}}catch{fail(new Error('Invalid approved-driver response'));}});
    const request=(method,params,timeout=20000)=>new Promise((resolve,reject)=>{
      if(signal.aborted || child.exitCode!==null) {reject(new Error('Approved operation cancelled'));return;}
      const id=++serial;
      const timer=setTimeout(()=>{waiters.delete(id);reject(new Error('Approved action timed out; effects unknown. Do not replay.'));},timeout);
      waiters.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');
    });
    const init=await request('initialize',{protocolVersion:'2024-11-05',capabilities:{},clientInfo:{name:'strata-human-approved-once',version:'1'}});
    if(!init?.serverInfo) throw new Error('Approved driver initialization failed.');
    child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');
    const state=await request('tools/call',{name:'get_window_state',arguments:{pid:args.pid,window_id:args.window_id,include_screenshot:true,max_image_dimension:captureDimension}});
    const picture=state?.content?.find(item=>item.type==='image'&&item.mimeType==='image/png');
    const stateMeta=state.structuredContent ?? {};
    if(state?.isError || !picture || targetPixels(picture.data,frozen,name)!==expectedPixels
      || JSON.stringify(stateMeta.window_bounds)!==JSON.stringify(frame.bounds) || signal.aborted)
      throw new Error('Window changed while approval was pending. No input dispatched; inspect a fresh screenshot.');
    // Capture IDs belong to this child, never reuse another process's token.
    delete approved.capture_id;
    const meta=state.structuredContent ?? state.content?.flatMap(x=>{try{return x.type==='text'?[JSON.parse(x.text)]:[];}catch{return [];}}).find(x=>x.capture_id);
    if(captureTools.has(name) && meta?.capture_id) approved.capture_id=meta.capture_id;
    const began=performance.now();
    assertOwned();
    const result=await request('tools/call',{name,arguments:approved},Math.max(20000,deliveryBudget+5000));
    if(name==='type_text'&&!result?.isError) {
      await settleTyping(Math.max(0,deliveryBudget-(performance.now()-began)),signal);
      result.content??=[];
      result.content.push({type:'text',text:'CUA_TEXT_DELIVERY: the driver key-stream interval was awaited before closing its owner. This is not text read-back proof. Inspect the complete target text before sending or continuing; never replay an uncertain insertion.'});
    }
    return result;
  } finally {
    fail(new Error('Approval consumed.'));
    lines?.close();child?.stdin.end();
    if(child && child.exitCode===null && child.pid) await new Promise(done=>{
      const timer=setTimeout(()=>{child.kill();done();},3000);
      child.once('exit',()=>{clearTimeout(timer);done();});
    });
    if(directory && dirname(resolve(directory))===resolve(tmpdir()) && basename(directory).startsWith('strata-cua-approved-'))
      await rm(directory,{recursive:true,force:true}).catch(()=>{});
  }
}
