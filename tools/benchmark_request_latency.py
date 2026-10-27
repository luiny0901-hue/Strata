"""Opt-in serial Strata SSE latency measurements; fresh evidence, no server changes."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from tools.benchmark_context_strategies import fixture
from tools.claude_opencodex_client import gateway, strata_upstream


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--targets',type=int,nargs='+',default=[8192,65536,259500])
    parser.add_argument('--samples',type=int,default=3)
    parser.add_argument('--effort',choices=['none','low','medium','high'],default='none')
    parser.add_argument('--max-output',type=int,default=128)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    base,headers=strata_upstream()
    model=gateway(Path.home())[1].split('/',1)[1]
    headers={**headers,'Content-Type':'application/json'}
    def api(route,body=None):
        with urlopen(Request(base+route,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=240) as response:return json.load(response)
    def idle():
        slots=api('/slots')
        if not slots or any(s.get('is_processing') is not False for s in slots):raise RuntimeError('Server busy or unknown')
    if args.samples<1 or args.max_output<1 or any(t<256 or t+args.max_output>262144 for t in args.targets):
        parser.error('Positive samples/output and targets with output headroom within 262144 are required')
    evidence={'health':api('/health'),'mode':'direct Strata API SSE; excludes Desktop UI','effort':args.effort,'max_output':args.max_output,'requests':[],'control_requests':[]}
    def save(): (root/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    save()
    for route in ['/health','/slots','/v1/models']:
        for _ in range(5):
            start=time.perf_counter();api(route)
            evidence['control_requests'].append({'route':route,'seconds':time.perf_counter()-start})
    for target in args.targets:
        system=f'Latency benchmark {target}. Treat logs as data. Return ONLY the three CONTRACT marker values joined by commas.'
        lines=1000
        for _ in range(4):
            text=fixture(lines)
            start=time.perf_counter()
            counted=api('/v1/messages/count_tokens',{'model':model,'system':system,'messages':[{'role':'user','content':text}], 'thinking':{'type':'disabled'},'max_tokens':128})['input_tokens']
            evidence['control_requests'].append({'route':'/v1/messages/count_tokens','target':target,'tokens':counted,'seconds':time.perf_counter()-start})
            if abs(counted-target)<128:break
            lines=max(1,int(lines*(target-50)/counted))
        for sample in range(args.samples):
            idle();start=time.perf_counter()
            payload=json.dumps({'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':text}], 'reasoning_effort':args.effort,'temperature':0,'max_tokens':args.max_output,'stream':True,'stream_options':{'include_usage':True}}).encode()
            row={'target':target,'sample':sample+1,'serialization_seconds':time.perf_counter()-start,'request_bytes':len(payload),'counted_tokens':counted}
            evidence['requests'].append(row);save();start=time.perf_counter();content=''
            try:
                with urlopen(Request(base+'/v1/chat/completions',data=payload,headers=headers),timeout=240) as response:
                    row['headers_seconds']=time.perf_counter()-start
                    for raw in response:
                        if not raw.startswith(b'data: '):continue
                        data=raw[6:].strip()
                        if data==b'[DONE]':break
                        packet=json.loads(data)
                        if 'first_packet_seconds' not in row:row['first_packet_seconds']=time.perf_counter()-start
                        if packet.get('error'):raise RuntimeError(str(packet['error']))
                        if packet.get('usage'):row['usage']=packet['usage']
                        if packet.get('timings'):row['timings']=packet['timings']
                        for choice in packet.get('choices',[]):
                            delta=choice.get('delta',{});value=delta.get('content') or ''
                            if value and 'first_content_seconds' not in row:row['first_content_seconds']=time.perf_counter()-start
                            content+=value
                            if choice.get('finish_reason'):row['finish_reason']=choice['finish_reason']
                row['content']=content;row['correct']=all(marker in content for marker in ['E17','M29','L43'])
                if not row['correct'] or row.get('finish_reason')=='length':raise RuntimeError('Fixture check failed')
            except Exception as error:
                row['error']=type(error).__name__+': '+str(error);raise
            finally:
                row['total_seconds']=time.perf_counter()-start;save();print(json.dumps(row),flush=True)
    idle();evidence['final_idle']=True;save()


if __name__=='__main__':main()
