"""Opt-in installed OpenCode + real supervisor + restartable CPU mock model.

No production server/model/config is used. Every attempt needs a fresh output directory.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.test_strata_server_supervisor import FIXTURE, free_port
from tools.strata_server_supervisor import Supervisor, control_handler
from tools.configure_strata_server_lifecycle import configure
from tools.opencode_runtime_assets import prepare_runtime_assets
from tools.test_autonomy_soak import resources
from http.server import ThreadingHTTPServer


POST = '''
 def do_POST(self):
  from pathlib import Path
  received=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  record=Path(sys.argv[2]);history=json.loads(record.read_text()) if record.exists() else []
  if received.get('tools'):
   history.append(received);record.write_text(json.dumps(history))
  if not received.get('tools'):
   delta={'content':'Fixture title'};finish='stop'
  elif len(history)%2==1:
   turn=(len(history)+1)//2
   delta={'tool_calls':[{'index':0,'id':'restart_call_'+str(turn),'type':'function','function':{'name':'strata_restart_server','arguments':json.dumps({'operation_id':'acp-owned-restart-'+str(turn),'checkpoint':'Saved source.py; remaining: confirm restart and final report for turn '+str(turn)})}}]}
   finish='tool_calls'
  else:
   encoded=json.dumps(received)
   content='RESTART_FOLLOWUP_OK' if 'STRATA_RESTART_READY' in encoded else 'RESTART_FAILURE_HANDLED' if 'STRATA_RESTART_FAILED' in encoded else 'RESTART_RESULT_MISSING'
   delta={'content':content};finish='stop'
  raw=('data: '+json.dumps({'id':'fixture','object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]})+'\\n\\n'+'data: '+json.dumps({'choices':[{'index':0,'delta':{},'finish_reason':finish}]})+'\\n\\ndata: [DONE]\\n\\n').encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--turns',type=int,default=1)
    parser.add_argument('--fail-restart',action='store_true')
    args=parser.parse_args()
    if not 1<=args.turns<=200: parser.error('turns must be 1..200')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    source=root/'mock.py';source.write_text(FIXTURE.replace(' def do_GET(self):',POST+' def do_GET(self):'),encoding='utf-8')
    key=root/'api-key';key.write_text('fixture-key',encoding='utf-8')
    token=root/'control-key';token.write_text('a'*64,encoding='utf-8')
    port=free_port();history=root/'requests.json'
    supervisor=Supervisor(root,[sys.executable,str(source),str(port),str(history)],f'http://127.0.0.1:{port}',key,'fixture',ready_timeout=10)
    server=ThreadingHTTPServer(('127.0.0.1',0),control_handler(supervisor,'a'*64))
    config=root/'config';config.mkdir()
    settings={'update':'disable','model':'test/fixture','plugins':[],
              'permissions':[{'action':'*','resource':'*','effect':'allow'}],
              'providers':{'test':{'name':'Test','package':'aisdk:@ai-sdk/openai-compatible',
              'settings':{'apiKey':'fixture-key','baseURL':f'http://127.0.0.1:{port}/v1'},
              'models':{'fixture':{'name':'Fixture','capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':100000,'output':1000}}}}}}
    for dest,content in prepare_runtime_assets(settings,config,names=('acp',)).items():
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    (config/'opencode.json').write_text(json.dumps(settings),encoding='utf-8')
    configure(config/'opencode.json',f'http://127.0.0.1:{server.server_port}',token)
    (root/'models.json').write_text('{}')
    env=dict(os.environ)
    for name in ('OPENCODE_CONFIG','OPENCODE_CONFIG_CONTENT','OPENCODE_CLI_CONFIG_CONTENT'):
        env.pop(name,None)
    env.update(HOME=str(root),USERPROFILE=str(root),OPENCODE_TEST_HOME=str(root),
        OPENCODE_CONFIG_DIR=str(config),OPENCODE_DB=str(root/'opencode.db'),
        OPENCODE_DISABLE_AUTOUPDATE='true',OPENCODE_DISABLE_FILEWATCHER='true',
        OPENCODE_DISABLE_MODELS_FETCH='true',OPENCODE_MODELS_PATH=str(root/'models.json'),
        OPENCODE_ACP_FOREGROUND_GUARD='1',OPENCODE_ACP_TURN_GUARD='1')
    for name,folder in [('XDG_CONFIG_HOME','xdg-config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:
        env[name]=str(root/folder)
    child=None;events=[];inbox=queue.Queue()
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    stderr=(root/'stderr.log').open('w',encoding='utf-8')
    try:
        supervisor.start();old_pid=supervisor.process.child.pid;thread.start()
        if args.fail_restart:
            def failed_ready():raise RuntimeError('injected readiness failure')
            supervisor.wait_ready=failed_ready
        child=subprocess.Popen([args.binary,'acp'],cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf-8')
        def read():
            for line in child.stdout:
                event=json.loads(line);events.append(event);inbox.put(event)
        threading.Thread(target=read,daemon=True).start()
        def send(value):
            child.stdin.write(json.dumps(value)+'\n');child.stdin.flush()
        def rpc(number,method,params):
            send({'jsonrpc':'2.0','id':number,'method':method,'params':params})
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                event=inbox.get(timeout=max(.1,deadline-time.monotonic()))
                if event.get('method')=='session/request_permission':
                    option=next(o for o in event['params']['options'] if o['kind']=='allow_once')
                    send({'jsonrpc':'2.0','id':event['id'],'result':{'outcome':{'outcome':'selected','optionId':option['optionId']}}})
                if event.get('id')==number and 'method' not in event:
                    if 'error' in event: raise RuntimeError(event['error'])
                    return event['result']
            raise TimeoutError(method)
        rpc(1,'initialize',{'protocolVersion':1,'clientCapabilities':{},'clientInfo':{'name':'restart-regression','version':'1'}})
        session=rpc(2,'session/new',{'cwd':str(root),'mcpServers':[]})
        samples=[]
        for turn in range(1,args.turns+1):
            began=time.monotonic();before=len(events)
            result=rpc(2+turn,'session/prompt',{'sessionId':session['sessionId'],'prompt':[{'type':'text','text':f'Turn {turn}: restart the managed fixture server, await readiness, and report the result.'}]})
            assert result['stopReason']=='end_turn',result
            assert supervisor.snapshot()['state']==('failed' if args.fail_restart else 'ready'),supervisor.snapshot()
            assert supervisor.snapshot()['operation_id']==f'acp-owned-restart-{turn}'
            assert supervisor.process.child.pid!=old_pid,'server child was not replaced'
            old_pid=supervisor.process.child.pid
            assert len(json.loads(history.read_text()))==2*turn,'unexpected model replay/retry'
            expected='RESTART_FAILURE_HANDLED' if args.fail_restart else 'RESTART_FOLLOWUP_OK'
            assert expected in json.dumps(events[before:]),'same-turn follow-up did not receive expected tool result'
            if args.fail_restart:
                updates=[e.get('params',{}).get('update',{}) for e in events[before:]]
                assert any(u.get('sessionUpdate')=='tool_call_update' and u.get('status')=='failed' for u in updates),'native ACP tool failure not visible'
            sample={'turn':turn,'seconds':round(time.monotonic()-began,3),'acp_resources':resources(int(child._handle)) if os.name=='nt' else {}}
            samples.append(sample)
            (root/'continuous-results.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
            if turn%10==0:print(json.dumps(sample),flush=True)
        outcome='failed native tool reported to ACP and handled' if args.fail_restart else 'authenticated readiness and same-turn continuation'
        print(f'PASS: {args.turns} turns in one installed ACP session; {2*args.turns} model requests; owned process replacements; {outcome}; final update before each end_turn')
    finally:
        (root/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
        if child:
            child.stdin.close()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill();child.wait(timeout=10)
        if thread.is_alive(): server.shutdown();thread.join()
        server.server_close()
        if supervisor.worker: supervisor.worker.join(timeout=15)
        supervisor.stopping.set();supervisor.process.stop();supervisor.log.close();stderr.close()


if __name__=='__main__':
    main()
