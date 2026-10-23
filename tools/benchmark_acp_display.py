"""Synthetic ACP byte/throughput stress; does not measure Rider rendering."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    def encode(value):return (json.dumps(value,ensure_ascii=False)+'\n').encode()
    thoughts=[encode({'method':'session/update','params':{'update':{'sessionUpdate':'agent_thought_chunk','content':{'type':'text','text':'생각 데이터 '*40}}}}) for _ in range(5000)]
    final=[encode({'method':'session/update','params':{'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'완료 보고\n'+'LONG_REPORT\n'*8000}}}}),encode({'method':'session/request_permission','id':11,'params':{'options':[]}}),encode({'method':'session/update','params':{'update':{'sessionUpdate':'tool_call_update','status':'completed'}}}),encode({'id':7,'result':{'stopReason':'end_turn'}})]
    raw=b''.join(thoughts+final);expected=b''.join(final);fixture=root/'fixture.jsonl';fixture.write_bytes(raw)
    child=root/'emit.py';child.write_text('import sys\nfrom pathlib import Path\nsys.stdout.buffer.write(Path(sys.argv[1]).read_bytes())\nsys.stdout.buffer.flush()\n',encoding='utf-8')
    base=[sys.executable,str(child),str(fixture)];proxy=Path(__file__).parent/'opencode/acp_compact_display.py';rows=[]
    for sample in range(3):
        for mode in (('direct','compact') if sample%2==0 else ('compact','direct')):
            command=base if mode=='direct' else [sys.executable,str(proxy),'--',*base]
            start=time.perf_counter();result=subprocess.run(command,input=b'',capture_output=True,timeout=20);elapsed=time.perf_counter()-start
            correct=result.returncode==0 and result.stdout==(raw if mode=='direct' else expected)
            rows.append({'sample':sample+1,'mode':mode,'seconds':elapsed,'bytes':len(result.stdout),'pass':correct})
            (root/'results.json').write_text(json.dumps({'notes':'5000 synthetic thought notifications plus long final report/permission/tool/final-response; process startup included; no Rider GUI','rows':rows},indent=2),encoding='utf-8')
            if not correct:raise RuntimeError('Protocol/report mismatch')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
