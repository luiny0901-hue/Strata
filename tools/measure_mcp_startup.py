"""Measure configured MCP initialization/catalog only; never call application tools."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def measure(command, environment):
    start=time.monotonic()
    child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env={**os.environ,**environment})
    inbox=queue.Queue()
    def read():
        for line in child.stdout:
            try: inbox.put(json.loads(line))
            except ValueError: pass
    threading.Thread(target=read,daemon=True).start()
    def drain_errors():
        for _ in child.stderr:
            pass
    threading.Thread(target=drain_errors,daemon=True).start()
    def rpc(number,method,params):
        child.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n');child.stdin.flush()
        deadline=time.monotonic()+20
        while True:
            response=inbox.get(timeout=max(.001,deadline-time.monotonic()))
            if response.get('id')==number:
                if 'error' in response: raise RuntimeError('MCP protocol error')
                return response['result']
    try:
        rpc(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'strata-startup-measure','version':'1'}})
        initialized=time.monotonic()
        child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');child.stdin.flush()
        result=rpc(2,'tools/list',{})
        return {'initialize_ms':round((initialized-start)*1000,2),'catalog_ms':round((time.monotonic()-initialized)*1000,2),'tool_count':len(result.get('tools',[])),'catalog_bytes':len(json.dumps(result).encode())}
    finally:
        child.stdin.close()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=5)
            else:child.kill()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/opencode/opencode.json')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Use a new evidence output file')
    config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    results={}
    for name,server in config.get('mcp',{}).get('servers',{}).items():
        if server.get('disabled') or server.get('type')!='local':continue
        try:results[name]=measure(server['command'],server.get('environment',{}))
        except Exception as error:results[name]={'error_type':type(error).__name__}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':main()
