// Initial discovery only: no model warm-up and no work on subsequent turns.
export async function settleMcp(context,{expected=()=>[],timeoutMs=15000,quietMs=200,pollMs=50,now=()=>performance.now(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))}={}) {
  const start=now();let changed=start,fingerprint,pending=[];
  const deadline=Symbol('MCP startup deadline');
  const bounded=async operation=>{
    let timer;
    try {
      return await Promise.race([
        Promise.resolve().then(operation),
        new Promise(resolve=>{timer=setTimeout(()=>resolve(deadline),Math.max(0,timeoutMs-(now()-start)));}),
      ]);
    } finally {clearTimeout(timer);}
  };
  while(now()-start<timeoutMs) {
    const response=await bounded(()=>context.mcp.list());
    if(response===deadline)return {settled:false,seconds:(now()-start)/1000,pending:[...new Set(pending)],stage:'mcp.list'};
    const servers=response.data??response;
    if(!Array.isArray(servers))throw new Error('MCP list returned an unsupported shape');
    const byName=new Map(servers.map(item=>[item.name,item]));
    pending=expected().filter(name=>!byName.has(name)||byName.get(name).status?.status==='pending');
    pending.push(...servers.filter(item=>item.status?.status==='pending').map(item=>item.name));
    if(!pending.length) {
      const tools=await bounded(()=>context.tool.list());
      if(tools===deadline)return {settled:false,seconds:(now()-start)/1000,pending:[],stage:'tool.list'};
      const next=JSON.stringify(tools.map(tool=>({id:tool.id,name:tool.name,input:tool.input,description:tool.description})).sort((a,b)=>String(a.id).localeCompare(String(b.id))));
      if(next!==fingerprint){fingerprint=next;changed=now();}
      if(now()-changed>=quietMs)return {settled:true,seconds:(now()-start)/1000,servers:servers.length,tools:tools.length};
    } else {fingerprint=undefined;changed=now();}
    await pause(Math.min(pollMs,Math.max(0,timeoutMs-(now()-start))));
  }
  return {settled:false,seconds:(now()-start)/1000,pending:[...new Set(pending)]};
}
