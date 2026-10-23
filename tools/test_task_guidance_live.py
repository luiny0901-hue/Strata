"""Opt-in live task-policy outcomes. No GUI, files, generated tools or deployment."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request,urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reasoning-effort',choices=['none','high'],default='none')
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    repo=Path(__file__).resolve().parents[1]
    result=subprocess.run(['node','--input-type=module','-e',"import {taskInstruction} from './examples/opencode/output-recovery/index.js';console.log(JSON.stringify(taskInstruction));"],cwd=repo,capture_output=True,text=True,encoding='utf-8',check=True)
    policy=json.loads(result.stdout)
    source=repo/'examples/opencode'
    base_system='\n'.join((source/name).read_text(encoding='utf-8') for name in ('KOREAN_INSTRUCTIONS.md','STRATA_SESSION_RECOVERY_KO.md'))
    system=base_system+'\n'+policy
    cfg=json.loads((Path.home()/'.config/opencode/opencode.json').read_text(encoding='utf-8'))
    provider,model=cfg['model'].split('/',1);settings=cfg['providers'][provider]['settings'];base=settings['baseURL'].rstrip('/').removesuffix('/v1');key=settings['apiKey']
    if key.startswith('{file:'):key=Path(key[6:-1]).expanduser().read_text(encoding='utf-8').strip()
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    def api(route,body=None):
        with urlopen(Request(base+route,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=180) as response:return json.load(response)
    report={'mode':'compact conditional policy; actual response outcomes, no classifier tool','effort':args.reasoning_effort,'health':api('/health'),'cases':[]}
    def persist(): (root/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    report['policy_characters']=len(policy);report['counted_prompt_tokens']={}
    for label,sys in [('baseline',base_system),('conditional',system)]:
        report['counted_prompt_tokens'][label]=api('/v1/messages/count_tokens',{'model':model,'system':sys,'messages':[{'role':'user','content':'두 정수를 더하는 Python 함수를 답해줘.'}],'thinking':{'type':'disabled'},'max_tokens':128})['input_tokens']
    def run(label,messages,check):
        slots=api('/slots')
        if not slots or any(s.get('is_processing') is not False for s in slots):raise RuntimeError('Server busy; stop')
        start=time.perf_counter();row={'label':label};report['cases'].append(row);persist()
        try:
            result=api('/v1/chat/completions',{'model':model,'messages':[{'role':'system','content':system},*messages],'reasoning_effort':args.reasoning_effort,'temperature':0,'max_tokens':2048 if args.reasoning_effort=='none' else 4096,'stream':False})
            choice=result['choices'][0];message=choice['message'];text=message.get('content') or ''
            row.update(message=message,usage=result.get('usage'),timings=result.get('timings'),finish_reason=choice.get('finish_reason'))
            row['pass']=not message.get('tool_calls') and choice.get('finish_reason')!='length' and bool(check(text))
        except Exception as error:
            row['error']=type(error).__name__+': '+str(error);raise
        finally:
            row['seconds']=time.perf_counter()-start;persist();print(json.dumps({'label':label,'pass':row.get('pass'),'seconds':row['seconds']}),flush=True)
    cases=[
      ('code','Python으로 두 정수를 더하는 함수만 답해줘.',lambda t:'def ' in t and 'return' in t),
      ('web','웹소설 독자용 웹사이트의 작품 목록 HTML 예시를 li 한 개, 3줄 이내로만 답해줘. 소설 본문은 쓰지 마.',lambda t:'<li' in t and '하린' not in t),
      ('question','소설을 써줄 수 있어? 지금은 작성하지 말고 가능한 작업만 짧게 설명해줘.',lambda t:'소설' in t and len(t)<1400 and '하린' not in t),
      ('quote','파이썬 문자열 s = "소설을 써줘"의 따옴표 이스케이프 방법만 짧게 설명해줘.',lambda t:'소설' in t and ('\\' in t or "'" in t)),
      ('negation','소설을 쓰지 말고 소설 게시판에서 페이지 이동 시 목록이 중복되는 코드 오류의 원인만 세 문장 이내로 설명해줘.',lambda t:'중복' in t and '하린' not in t),
      ('draft','하린이 녹색 우산을 잃어버리는 한국어 단편소설을 200자 정도 써줘.',lambda t:'하린' in t and '녹색' in t and '우산' in t and '<html' not in t),
      ('revision','다음 소설 원고를 맞춤법만 고쳐줘. 방언과 이름, 사건은 유지하고 교정 문장만 답해: 하린은 "내 우산 어딨노"라며 문앞에 섯다.',lambda t:'하린' in t and '어딨노' in t and '문 앞에 섰다' in t and len(t)<200),
      ('mixed','하린이 등장하는 단편소설 첫 문단을 100자 쓰고, 그 원고를 게시할 HTML 예시도 3줄 이내로 함께 답해줘.',lambda t:'하린' in t and '<' in t and '>' in t),
      ('compressed-continuation','압축 상태: 장편소설 집필 중. 하린은 우산을 잃었고 연우는 편지 존재를 모른다. 1인칭 과거형, 미회수 복선은 녹색 우산 속 편지. 1장 저장 완료, 2장 미작성. 2장 첫 장면을 100자 정도만 이어 써줘.',lambda t:'우산' in t or '편지' in t),
    ]
    for label,text,check in cases:run(label,[{'role':'user','content':text}],check)
    known=[{'role':'user','content':'하린이 녹색 우산을 잃어버리는 소설을 1인칭 과거형으로 써줘.'},{'role':'assistant','content':'나는 녹색 우산을 찾으려고 문을 나섰다. 바닥에는 낯선 편지가 떨어져 있었다.'}]
    run('continuation',[*known,{'role':'user','content':'같은 시점과 문체로 다음 문단만 100자 정도 이어 써줘.'}],lambda t:'편지' in t or '우산' in t)
    run('switch-back-code',[*known,{'role':'user','content':'소설 집필은 여기서 끝이야. 이제 배열 중복 항목을 제거하는 JavaScript 함수만 답해줘.'}],lambda t:'Set' in t or 'filter' in t)
    report['passed']=sum(r.get('pass',False) for r in report['cases']);report['total']=len(report['cases']);persist()
    if report['passed']!=report['total']:raise SystemExit('Outcome mismatch preserved; inspect before deployment')


if __name__=='__main__':main()
