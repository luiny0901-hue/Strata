"""Measure configured CUA MCP handshake/catalog only. Never call a GUI tool."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((Path.home()/'.config/opencode/opencode.json').read_text(encoding='utf-8'))
    server=cfg['mcp']['servers']['cua-driver'];results=[]
    if server.get('disabled'):raise RuntimeError('Configured CUA disabled')
    for sample in range(3):
        row={'sample':sample+1};start=time.perf_counter();inbox=queue.Queue()
        with (root/f'stderr-{sample+1}.log').open('w',encoding='utf-8') as stderr:
            child=subprocess.Popen(server['command'],env={**os.environ,**server.get('environment',{})},stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf-8')
            def read(stream):
                for line in stream:
                    try:inbox.put(json.loads(line))
                    except ValueError:inbox.put({'invalid_json':True})
                inbox.put({'closed':True})
            reader=threading.Thread(target=read,args=(child.stdout,),daemon=True);reader.start()
            def send(value):child.stdin.write(json.dumps(value)+'\n');child.stdin.flush()
            def request(number,method,params):
                before=time.perf_counter();send({'jsonrpc':'2.0','id':number,'method':method,'params':params});deadline=time.monotonic()+30
                while True:
                    response=inbox.get(timeout=max(.001,deadline-time.monotonic()))
                    if response.get('closed') or response.get('invalid_json'):raise RuntimeError('Invalid/closed MCP output')
                    if response.get('id')==number:
                        if response.get('error'):raise RuntimeError(str(response['error']))
                        row[method+'_seconds']=time.perf_counter()-before
                        return response['result']
                    if time.monotonic()>deadline:raise TimeoutError(method)
            try:
                request(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'latency-metadata-only','version':'1'}})
                row['spawn_to_initialized_seconds']=time.perf_counter()-start
                send({'jsonrpc':'2.0','method':'notifications/initialized'})
                for number in (2,3,4):
                    result=request(number,'tools/list',{})
                    if sample==0 and number==2:
                        (root/'catalog.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    row.setdefault('catalog_samples',[]).append({'seconds':row['tools/list_seconds'],'tools':len(result['tools']),'json_bytes':len(json.dumps(result).encode())})
                row['pass']=True
            except Exception as error:
                row['error']=type(error).__name__+': '+str(error);raise
            finally:
                child.stdin.close()
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=10)
                    child.wait(timeout=5)
                reader.join(timeout=2);child.stdout.close()
                row['exitcode']=child.returncode;row['total_including_cleanup_seconds']=time.perf_counter()-start
                results.append(row);(root/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
                print(json.dumps(row),flush=True)


if __name__=='__main__':main()
