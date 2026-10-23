"""Opt-in installed OpenCode + local Strata file I/O pipeline, isolated fixtures.

Only read/edit/write tools are offered; no GUI/MCP/shell or existing project work.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import sqlite3
import shutil


def verified_readback(events, expected):
    """Require a successful result-file read after the completed write/edit."""
    names = {}
    inputs = set()
    changed = None
    verified = False
    for item in events:
        update = item['event'].get('params', {}).get('update', {})
        call = update.get('toolCallId')
        if update.get('title'):
            names[call] = update['title']
        locations = [location.get('path', '').replace('\\', '/').rsplit('/', 1)[-1] for location in update.get('locations', [])]
        if update.get('status') != 'completed':
            continue
        name = names.get(call)
        if name == 'read':
            inputs.update(locations)
        if 'result.txt' not in locations:
            continue
        if name in ('edit', 'write'):
            changed = item['seconds']
            verified = False
        elif name == 'read' and changed is not None and item['seconds'] > changed:
            text = '\n'.join(part.get('content', {}).get('text', '') for part in update.get('content', []) if part.get('type') == 'content')
            verified = expected.rstrip('\n') in text
    return verified, {'a.txt', 'b.txt'} <= inputs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--compact-display',action='store_true')
    p.add_argument('--effort',choices=['none','low','medium','high'],default='none')
    p.add_argument('--delayed-mcp-ms',type=int,default=0)
    p.add_argument('--mcp-startup-barrier-ms',type=int,default=0)
    p.add_argument('--explicit-edit',action='store_true',help='Use an explicit TOTAL=42 to TOTAL=43 follow-up for paired trials')
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((Path.home()/'.config/opencode/opencode.json').read_text(encoding='utf-8'))
    provider,model=cfg['model'].split('/',1);selected=copy.deepcopy(cfg['providers'][provider])
    keyref=selected['settings']['apiKey']
    if keyref.startswith('{file:'):
        selected['settings']['apiKey']='{file:'+str(Path(keyref[6:-1]).expanduser())+'}'
    selected['models']={model:selected['models'][model]}
    selected['models'][model].setdefault('body',{})['reasoning_effort']=args.effort
    project=root/'project';project.mkdir()
    (project/'a.txt').write_text('17\n');(project/'b.txt').write_text('25\n')
    unrelated={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in (project/'a.txt',project/'b.txt')}
    for index in range(256):
        f=project/f'unrelated-{index:03d}.txt';f.write_text('PRESERVE\n'*128);unrelated[f]=hashlib.sha256(f.read_bytes()).hexdigest()
    plugin=root/'bounded-tools';plugin.mkdir();(plugin/'package.json').write_text('{"name":"strata-io-benchmark","type":"module"}')
    (plugin/'index.js').write_text("export default {id:'strata.io-benchmark',async setup(ctx){await ctx.session.hook('context',e=>{e.tools=Object.fromEntries(Object.entries(e.tools).filter(([name])=>['read','write','edit'].includes(name)));});}};",encoding='utf-8')
    if args.delayed_mcp_ms:
        content=(plugin/'index.js').read_text(encoding='utf-8').replace("['read','write','edit'].includes(name)","(['read','write','edit'].includes(name)||name.endsWith('metadata_probe'))")
        (plugin/'index.js').write_text(content,encoding='utf-8')
    config=root/'config';config.mkdir()
    settings={'model':cfg['model'],'providers':{provider:selected},'agents':{'build':{'steps':16}},'permissions':[{'action':'*','resource':'*','effect':'allow'}],'plugins':[str(plugin)],'instructions':[],'mcp':{'servers':{}}}
    if args.delayed_mcp_ms:
        if not 1<=args.delayed_mcp_ms<=10000:raise ValueError('delayed MCP must be 1..10000ms')
        fixture=root/'delayed-mcp.cjs'
        fixture.write_text('''const rl=require('readline').createInterface({input:process.stdin});
rl.on('line',line=>{const m=JSON.parse(line);const send=result=>console.log(JSON.stringify({jsonrpc:'2.0',id:m.id,result}));
if(m.method==='initialize')send({protocolVersion:m.params.protocolVersion,serverInfo:{name:'delayed-fixture',version:'1'},capabilities:{tools:{}}});
if(m.method==='tools/list')setTimeout(()=>send({tools:[{name:'metadata_probe',description:'Read-only benchmark metadata; no GUI or filesystem writes.',inputSchema:{type:'object',properties:{}}}]}),Number(process.argv[2]));
});rl.on('close',()=>process.exit(0));''',encoding='utf-8')
        settings['mcp']['servers']['delayed']={'type':'local','command':[shutil.which('node'),str(fixture),str(args.delayed_mcp_ms)],'codemode':False}
        guard=Path(__file__).parents[1]/'examples/opencode/acp-foreground-guard'
        settings['plugins'].append({'package':str(guard),'options':{'mcpStartupBarrierMs':args.mcp_startup_barrier_ms,'mcpStartupReceipt':str(root/'startup-receipt.json')}})
    (config/'opencode.json').write_text(json.dumps(settings),encoding='utf-8')
    env=dict(os.environ)
    for key in ('OPENCODE_CONFIG','OPENCODE_CONFIG_CONTENT','OPENCODE_CLI_CONFIG_CONTENT'):env.pop(key,None)
    env.update({'HOME':str(root),'USERPROFILE':str(root),'OPENCODE_CONFIG_DIR':str(config),'OPENCODE_DB':str(root/'opencode.db'),'OPENCODE_TEST_HOME':str(root),'OPENCODE_DISABLE_AUTOUPDATE':'true','OPENCODE_DISABLE_FILEWATCHER':'true','OPENCODE_DISABLE_MODELS_FETCH':'true','OPENCODE_MODELS_PATH':str(root/'models.json')})
    if args.delayed_mcp_ms:env.update({'OPENCODE_ACP_FOREGROUND_GUARD':'1','OPENCODE_ACP_TURN_GUARD':'1'})
    (root/'models.json').write_text('{}')
    for key,folder in [('XDG_CONFIG_HOME','xdg-config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:env[key]=str(root/folder)
    command=[str(args.binary),'acp']
    if args.compact_display:command=[sys.executable,str(Path(__file__).parent/'opencode/acp_compact_display.py'),'--',*command]
    report={'mode':'installed ACP + real Strata, isolated read/edit/write tools; no Rider GUI','effort':args.effort+' (benchmark only)','delayed_mcp_ms':args.delayed_mcp_ms,'mcp_startup_barrier_ms':args.mcp_startup_barrier_ms,'explicit_edit':args.explicit_edit,'compact_display':args.compact_display,'rpc':[],'turns':[]};events=[];inbox=queue.Queue();origin=time.perf_counter()
    def save():
        (root/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    stderr=(root/'stderr.log').open('w',encoding='utf-8')
    child=subprocess.Popen(command,cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf-8')
    def read():
        for line in child.stdout:
            try:inbox.put(json.loads(line))
            except ValueError:inbox.put({'protocol_error':True})
        inbox.put({'closed':True})
    threading.Thread(target=read,daemon=True).start()
    def rpc(number,method,params):
        start=time.perf_counter();child.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n');child.stdin.flush()
        deadline=time.monotonic()+240
        while True:
            value=inbox.get(timeout=max(.001,deadline-time.monotonic()))
            if value.get('closed') or value.get('protocol_error'):raise RuntimeError('ACP closed/invalid output')
            if value.get('id')==number:
                report['rpc'].append({'method':method,'seconds':time.perf_counter()-start})
                if value.get('error'):raise RuntimeError(str(value['error']))
                return value['result']
            events.append({'seconds':time.perf_counter()-origin,'event':value})
    try:
        rpc(1,'initialize',{'protocolVersion':1,'clientCapabilities':{},'clientInfo':{'name':'strata-io-benchmark','version':'1'}})
        session=rpc(2,'session/new',{'cwd':str(project),'mcpServers':[]})
        tasks=[('Read a.txt and b.txt. Create result.txt containing exactly TOTAL=<their integer sum> followed by one newline. Read result.txt to verify it, then report completion briefly. Use only read/write/edit. Preserve all other files.', 'TOTAL=42\n'),('Read result.txt and increase its number by one. Preserve the TOTAL= format and trailing newline. Read it again to verify, then report briefly. Preserve all other files.', 'TOTAL=43\n')]
        if args.explicit_edit:tasks[1]=('Read result.txt and replace TOTAL=42 with TOTAL=43. Preserve exactly one trailing newline. Read the saved file to verify it, then report briefly. Preserve all other files.','TOTAL=43\n')
        for index,(task,expected) in enumerate(tasks):
            begin_event=len(events)
            start=time.perf_counter();result=rpc(3+index,'session/prompt',{'sessionId':session['sessionId'],'prompt':[{'type':'text','text':task}]})
            actual=(project/'result.txt').read_text(encoding='utf-8') if (project/'result.txt').exists() else None
            updates=[e['event'].get('params',{}).get('update',{}) for e in events[begin_event:]]
            reads=sum(u.get('sessionUpdate')=='tool_call' and u.get('title')=='read' for u in updates)
            report_visible=any(u.get('sessionUpdate')=='agent_message_chunk' and u.get('content',{}).get('text') for u in updates)
            readback, inputs_read=verified_readback(events[begin_event:],expected)
            exact_bytes=(project/'result.txt').read_bytes()==expected.encode('utf-8') if (project/'result.txt').exists() else False
            good=exact_bytes and result.get('stopReason')=='end_turn' and readback and (index>0 or inputs_read) and report_visible and all(hashlib.sha256(f.read_bytes()).hexdigest()==digest for f,digest in unrelated.items())
            report['turns'].append({'turn':index+1,'seconds':time.perf_counter()-start,'stop_reason':result.get('stopReason'),'read_calls':reads,'verified_readback':readback,'exact_bytes':exact_bytes,'report_visible':report_visible,'pass':good,'actual':actual});save()
            if not good:raise RuntimeError('File/finish/preservation check failed')
        with sqlite3.connect(f'file:{(root/"opencode.db").as_posix()}?mode=ro',uri=True) as db:
            report['model_rounds']=[json.loads(row[0]) for row in db.execute("select data from session_message where session_id=? and type='assistant' order by seq",(session['sessionId'],))]
            report['catalog_notices']=[json.loads(row[0]) for row in db.execute("select data from session_message where session_id=? and type='system' order by seq",(session['sessionId'],))]
        report['pass']=True;print(json.dumps({k:v for k,v in report.items() if k not in ('model_rounds','catalog_notices')},ensure_ascii=False),flush=True)
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error);raise
    finally:
        child.stdin.close()
        try:child.wait(timeout=15)
        except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
        stderr.close();save()


if __name__=='__main__':main()
