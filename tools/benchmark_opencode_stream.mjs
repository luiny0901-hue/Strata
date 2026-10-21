// CPU-only synthetic SSE benchmark; no model or server is launched.
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
const {recoverStream}=await import(pathToFileURL(path.resolve(process.argv[2] ?? 'examples/opencode/output-recovery/index.js')));
const encode=new TextEncoder();
const packet=(delta, finish_reason=null)=>'data: '+JSON.stringify({choices:[{index:0,delta,finish_reason}]})+'\n\n';
for (const mode of ['text','tool']) {
  const parts=[];
  if(mode==='tool') parts.push(packet({tool_calls:[{index:0,id:'call',type:'function',function:{name:'write',arguments:'{"content":"'}}]}));
  for(let i=0;i<6000;i++) parts.push(packet(mode==='tool'?{tool_calls:[{index:0,function:{arguments:'abcde'}}]}:{content:'abcde'}));
  if(mode==='tool') parts.push(packet({tool_calls:[{index:0,function:{arguments:'"}'}}]}));
  parts.push(packet({},mode==='tool'?'tool_calls':'stop'),'data: [DONE]\n\n');
  const bytes=encode.encode(parts.join(''));
  const samples=[];
  let digest;
  for(let n=0;n<8;n++) {
    let offset=0;
    const body=new ReadableStream({pull(c){if(offset>=bytes.length){c.close();return;} c.enqueue(bytes.slice(offset,offset+4096));offset+=4096;}});
    const start=performance.now();
    const result=await new Response(recoverStream(body,()=>1,()=>{})).arrayBuffer();
    if(n) samples.push(performance.now()-start);
    const hash=createHash('sha256').update(new Uint8Array(result)).digest('hex');
    if(digest && hash!==digest) throw new Error('Non-deterministic output');
    digest=hash;
  }
  samples.sort((a,b)=>a-b);
  console.log(JSON.stringify({mode,events:6000,median_ms:+samples[3].toFixed(2),sha256:digest}));
}
