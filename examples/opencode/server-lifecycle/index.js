import {readFile} from 'node:fs/promises';

export async function restartServer(input, execution, options) {
  const url = new URL(options.controlURL);
  if (url.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname)
      || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Restart control must be a loopback origin; remote clients use an authenticated SSH tunnel.');
  }
  const token = (await readFile(options.tokenFile, 'utf8')).trim();
  if (!/^[a-f0-9]{64}$/.test(token)) throw new Error('Invalid restart control token file');
  const signal = execution?.signal;
  signal?.throwIfAborted();
  const deadline = AbortSignal.timeout(900000);
  const combined = signal ? AbortSignal.any([signal, deadline]) : deadline;
  async function post(route, body, requestSignal = combined) {
    const response = await fetch(new URL(route,url), {method:'POST',
      headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json'},
      body:JSON.stringify(body), signal:AbortSignal.any([requestSignal,AbortSignal.timeout(5000)])});
    if (!response.ok) throw new Error(`Restart control ${route}: HTTP ${response.status}; inspect status before retrying.`);
    return response.json();
  }
  let submitted = false;
  try {
    // Once sent, cancellation/transport failure does not prove it was not accepted.
    submitted = true;
    let job = await post('/restart', input);
    while (true) {
      combined.throwIfAborted();
      if (!job || job.operation_id !== input.operation_id) throw new Error('Restart receipt does not match operation_id');
      if (['ready','failed','cancelled'].includes(job.state)) {
        const text = job.state === 'ready'
          ? 'STRATA_RESTART_READY: owned server restarted; authenticated model readiness confirmed. Continue only the saved unfinished task, inspect current files, and do not replay completed side effects.'
          : `STRATA_RESTART_${job.state.toUpperCase()}: ${job.error || 'request cancelled'}; unfinished task is not complete. Inspect the receipt before another restart.`;
        // This is a native OpenCode tool, not an MCP CallToolResult. The native
        // result has no isError flag: rejecting is required for failed tool UI.
        if (job.state !== 'ready') throw new Error(text);
        return {content:text};
      }
      await new Promise((resolve,reject)=>{
        const abort=()=>{clearTimeout(timer);reject(combined.reason);};
        const timer=setTimeout(()=>{combined.removeEventListener('abort',abort);resolve();},500);
        combined.addEventListener('abort',abort,{once:true});
        if(combined.aborted) abort();
      });
      job = await post('/status', {operation_id:input.operation_id});
    }
  } catch (error) {
    if (submitted) await post('/cancel',{operation_id:input.operation_id},AbortSignal.timeout(3000)).catch(()=>{});
    throw error;
  }
}

export default {
  id:'strata.server-lifecycle',
  async setup(context) {
    if (!context.options?.controlURL || !context.options?.tokenFile) return;
    await context.tool.transform(editor=>editor.add({
      id:'strata_restart_server', name:'strata_restart_server',
      description:'Restart only the externally managed Strata inference server after authorized source/config changes. Save files first. Supply a unique operation_id and a concise checkpoint of scope, completed/unfinished work, exact paths and pending validation. Reuse the same operation_id/checkpoint after uncertain delivery; never submit a new ID to blindly retry. Await this tool; do not kill the server through shell or end the turn while restarting. Does not grant new task permission.',
      input:{type:'object',properties:{operation_id:{type:'string',minLength:1,maxLength:128},checkpoint:{type:'string',minLength:1,maxLength:16000}},required:['operation_id','checkpoint'],additionalProperties:false},
      options:{codemode:false},
      execute:(input,execution)=>restartServer(input,execution,context.options),
    }));
  },
};
