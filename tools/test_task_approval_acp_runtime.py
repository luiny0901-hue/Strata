"""Installed ACP + task bridge + simulated approval/MCP/model. No GUI or GPU."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parents[1]
    module = (source / 'tools/cua-driver/opencode-task-approval.mjs').as_uri()
    probe = root / 'probe.mjs'
    probe.write_text('''import readline from 'node:readline';
import {appendFileSync} from 'node:fs';
import {TaskApproval} from MODULE;
const gate=new TaskApproval(process.env.STRATA_CUA_TASK_STATE);let approvals=0;
gate.confirmInChat=async()=>{approvals++;return true;};
const rl=readline.createInterface({input:process.stdin});
rl.on('line',async line=>{const m=JSON.parse(line);const send=result=>console.log(JSON.stringify({jsonrpc:'2.0',id:m.id,result}));
if(m.method==='initialize')send({protocolVersion:m.params.protocolVersion,serverInfo:{name:'task-probe',version:'1'},capabilities:{tools:{}}});
if(m.method==='tools/list')send({tools:[{name:'scope_probe',description:'Test-only simulated approval probe; no GUI.',inputSchema:{type:'object',properties:{},additionalProperties:false}}]});
if(m.method==='tools/call'){
 const sessionID=m.params?._meta?.['ai.opencode/sessionID'];const controller=new AbortController();let scope;
 try {scope=gate.bind(sessionID,controller);const allowed=await scope.authorize('simulated GUI',controller.signal);
 const row={sessionID,allowed,approvals,key:gate.current(sessionID)?.key};appendFileSync(process.argv[2],JSON.stringify(row)+'\\n');send({content:[{type:'text',text:JSON.stringify(row)}]});}
 catch(error){send({content:[{type:'text',text:error.message}],isError:true});}finally{scope?.close();}
}});rl.on('close',()=>{gate.close();process.exit(0);});
'''.replace('MODULE', json.dumps(module)), encoding='utf-8')
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            messages = body.get('messages', [])
            users = [i for i, message in enumerate(messages) if message['role'] == 'user']
            boundary = users[-1] if users else 0
            tools = sum(message['role'] == 'tool' for message in messages[boundary:])
            wanted = 2 if len(users) == 1 else 1
            selected = next((tool['function']['name'] for tool in body.get('tools', []) if tool['function']['name'].endswith('scope_probe')), None)
            if selected and tools < wanted:
                delta = {'tool_calls':[{'index':0,'id':f'probe_{len(requests)}','type':'function','function':{'name':selected,'arguments':'{}'}}]}
                finish = 'tool_calls'
            else:
                delta = {'content':'TASK_PROBE_COMPLETE'}
                finish = 'stop'
            requests.append({'tools':tools,'selected':selected,'finish':finish})
            chunks = [{'choices':[{'index':0,'delta':delta,'finish_reason':None}]}, {'choices':[{'index':0,'delta':{},'finish_reason':finish}]}]
            payload = ''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
            data = payload.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = root / 'config'
    config.mkdir()
    settings = {'model':'test/fixture','permissions':[{'action':'*','resource':'*','effect':'allow'}],
                'plugins':[{'package':str(source/'examples/opencode/acp-foreground-guard'),'options':{'mcpStartupBarrierMs':15000}}],
                'mcp':{'servers':{'approval':{'type':'local','command':[shutil.which('node'),str(probe),str(root/'probes.jsonl')],'codemode':False}}},
                'providers':{'test':{'name':'Fixture','package':'@opencode/ai/providers/openai-compatible',
                'settings':{'apiKey':'fixture','baseURL':f'http://127.0.0.1:{server.server_port}/v1'},
                'models':{'fixture':{'name':'Fixture','capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':100000,'output':1000}}}}}}
    (config/'opencode.json').write_text(json.dumps(settings), encoding='utf-8')
    (root/'models.json').write_text('{}')
    env = dict(os.environ)
    for key in ('OPENCODE_CONFIG','OPENCODE_CONFIG_CONTENT','OPENCODE_CLI_CONFIG_CONTENT'):
        env.pop(key, None)
    env.update({'HOME':str(root),'USERPROFILE':str(root),'OPENCODE_CONFIG_DIR':str(config),'OPENCODE_DB':str(root/'opencode.db'),
                'OPENCODE_TEST_HOME':str(root),'OPENCODE_MODELS_PATH':str(root/'models.json'),'OPENCODE_DISABLE_AUTOUPDATE':'true',
                'OPENCODE_DISABLE_MODELS_FETCH':'true','OPENCODE_ACP_FOREGROUND_GUARD':'1','OPENCODE_ACP_TURN_GUARD':'1'})
    for key, name in [('XDG_CONFIG_HOME','xdg'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:
        env[key] = str(root/name)
    errors = (root/'stderr.log').open('w', encoding='utf-8')
    child = subprocess.Popen([sys.executable,str(source/'tools/opencode/acp_compact_display.py'),'--',args.binary,'acp'],
                             cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8')
    inbox = queue.Queue()
    def read():
        for line in child.stdout:
            inbox.put(json.loads(line))
        inbox.put({'closed':True})
    threading.Thread(target=read, daemon=True).start()
    def rpc(number, method, params):
        child.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n')
        child.stdin.flush()
        end = time.monotonic()+60
        while time.monotonic() < end:
            reply = inbox.get(timeout=max(.01,end-time.monotonic()))
            if reply.get('closed'):
                raise RuntimeError('ACP closed')
            if reply.get('id') == number and 'method' not in reply:
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply['result']
        raise TimeoutError(method)
    result = {}
    try:
        rpc(1,'initialize',{'protocolVersion':1,'clientCapabilities':{},'clientInfo':{'name':'task-approval-test','version':'1'}})
        session = rpc(2,'session/new',{'cwd':str(root),'mcpServers':[]})
        for number in (3,4):
            answer = rpc(number,'session/prompt',{'sessionId':session['sessionId'],'prompt':[{'type':'text','text':'Run the simulated approval probe twice.' if number==3 else 'New task: run the simulated approval probe once.'}]})
            assert answer['stopReason']=='end_turn',answer
        rows = [json.loads(line) for line in (root/'probes.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows)==3,rows
        assert [row['approvals'] for row in rows]==[1,1,2],rows
        assert all(row['allowed'] and row['sessionID']==session['sessionId'] for row in rows),rows
        assert rows[0]['key']==rows[1]['key']!=rows[2]['key'],rows
        result={'pass':True,'approval_counts':[row['approvals'] for row in rows],'same_session':True,'scope':'installed OpenCode and ACP transport; simulated approval, MCP and model; no GUI/GPU'}
        print(json.dumps(result),flush=True)
    except Exception as error:
        result={'pass':False,'error':str(error)}
        raise
    finally:
        (root/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        (root/'requests.json').write_text(json.dumps(requests,indent=2),encoding='utf-8')
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        errors.close()
        server.shutdown()


if __name__ == '__main__':
    main()
