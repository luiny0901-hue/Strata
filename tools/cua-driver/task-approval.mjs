import {readFileSync,watch} from 'node:fs';
import {dirname,basename,join} from 'node:path';
import {writeFile,readFile,unlink} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';

export class TaskApproval {
  constructor(path,{read=readFileSync,alive=pid=>{try{process.kill(pid,0);return true;}catch{return false;}}}={}) {
    this.path=path;this.read=read;this.alive=alive;this.grants=new Set();this.denied=new Set();this.active=new Set();
    if(path) {
      try {this.watcher=watch(dirname(path),(_,file)=>{if(!file||String(file)===basename(path))this.refresh();});this.watcher.on('error',()=>{this.unavailable=true;this.revoke();});}
      catch {this.unavailable=true;}
    }
  }
  snapshot() {
    if(!this.path||this.unavailable||this.closed)return [];
    try {
      const state=JSON.parse(this.read(this.path,'utf8'));
      if(state.version!==1||!Number.isInteger(state.owner)||state.owner<=0||!this.alive(state.owner)||!Array.isArray(state.tasks))return [];
      return state.tasks.filter(task=>typeof task.sessionID==='string'&&/^[a-f0-9]{32}$/.test(task.key));
    } catch {return [];}
  }
  current(sessionID) {
    const tasks=this.snapshot().filter(task=>task.sessionID===sessionID);
    return tasks.length===1?tasks[0]:undefined;
  }
  refresh() {
    const valid=new Set(this.snapshot().map(task=>task.key));
    for(const key of this.grants)if(!valid.has(key))this.grants.delete(key);
    for(const key of this.denied)if(!valid.has(key))this.denied.delete(key);
    for(const item of this.active)if(!valid.has(item.key)||this.current(item.sessionID)?.key!==item.key){this.grants.delete(item.key);item.controller.abort();}
  }
  revoke() {
    this.grants.clear();
    this.denied.clear();
    for(const item of this.active)item.controller.abort();
  }
  async confirmInChat(task,preview,signal) {
    const base=join(dirname(this.path),`approval-${randomUUID()}`);
    const request=base+'.request',response=base+'.response';
    try {
      await writeFile(request,JSON.stringify({taskKey:task.key,sessionID:task.sessionID,preview}),{flag:'wx'});
      const deadline=Date.now()+120000;
      while(!signal.aborted&&Date.now()<deadline&&this.current(task.sessionID)?.key===task.key) {
        try {return JSON.parse(await readFile(response,'utf8')).accepted===true;} catch(error) {if(error.code!=='ENOENT')return false;}
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      return false;
    } finally {await Promise.allSettled([unlink(request),unlink(response)]);}
  }
  bind(sessionID,controller) {
    if(!this.path)return {authorize:undefined,close:()=>{}}; // Clients without request-state coordination use per-action approval.
    this.refresh();
    const task=this.current(sessionID);
    if(!task)throw new Error('CUA_TASK_REQUIRED: no unambiguous live request owns this action.');
    const item={key:task.key,sessionID,controller};this.active.add(item);
    const stillOwned=()=>!controller.signal.aborted&&this.current(sessionID)?.key===task.key;
    return {
      authorize:async(preview,signal,confirm)=>{
        if(!stillOwned())return false;
        if(this.grants.has(task.key))return true;
        if(this.denied.has(task.key))return false;
        const description=`현재 요청이 완료·취소되거나 연결이 끝날 때까지 CUA 전경 입력 전체를 허용합니다.\r\n여러 앱의 정확한 창에서 마우스·키보드를 사용할 수 있으며 사용자의 PC 사용을 방해할 수 있습니다.\r\n다음 사용자 요청에는 승인이 이어지지 않습니다. UAC/보안 데스크톱은 제외됩니다.\r\n작업 세션: ${sessionID}\r\n\r\n첫 동작:\r\n${preview}`;
        const accepted=await this.confirmInChat(task,description,signal);
        if(!stillOwned())return false;
        if(!accepted){this.denied.add(task.key);return false;}
        this.grants.add(task.key);return true;
      },
      assertOwned:()=>{if(!stillOwned())throw new Error('CUA task completed or cancelled; no further input is allowed.');},
      close:()=>this.active.delete(item),
    };
  }
  close(){this.closed=true;this.revoke();this.watcher?.close();}
}
