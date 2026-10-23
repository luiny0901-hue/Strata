"""Opt-in A/B fixtures. No server/config changes, arbitrary shell, or GUI input."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request,urlopen

from tools.benchmark_context_strategies import fixture,extract,EXPECTED


def edit_fixture(count=100):
    return '\n'.join(f'def value_{i:03d}():\n    return {i}\n' for i in range(count))


def verify_edit(code,count=100):
    expected=edit_fixture(count).replace('def value_050():\n    return 50','def value_050():\n    return 1050')
    return ast.dump(ast.parse(code))==ast.dump(ast.parse(expected))


def apply_exact(source,old,new):
    if not old or source.count(old)!=1:raise ValueError('Edit must match exactly once')
    return source.replace(old,new,1)


class Experiment:
    def __init__(self,root):
        self.root=root;root.mkdir(parents=True,exist_ok=False)
        cfg=json.loads((Path.home()/'.config/opencode/opencode.json').read_text(encoding='utf-8'))
        provider,self.model=cfg['model'].split('/',1);settings=cfg['providers'][provider]['settings']
        self.base=settings['baseURL'].rstrip('/').removesuffix('/v1');key=settings['apiKey']
        if key.startswith('{file:'):key=Path(key[6:-1]).expanduser().read_text(encoding='utf-8').strip()
        self.headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
        self.data={'requests':[],'notes':'Direct API experiments; reasoning none; no production policy changed.'}

    def api(self,route,body=None):
        with urlopen(Request(self.base+route,data=None if body is None else json.dumps(body).encode(),headers=self.headers),timeout=240) as response:return json.load(response)

    def save(self):
        (self.root/'results.json').write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')

    def idle(self):
        slots=self.api('/slots')
        if not slots or any(s.get('is_processing') is not False for s in slots):raise RuntimeError('Server busy; stop')

    def run(self,label,messages,tools=None,limit=512,check=None):
        self.idle();body={'model':self.model,'messages':messages,'temperature':0,'reasoning_effort':'none','max_tokens':limit,'stream':False}
        if tools:body['tools']=tools
        row={'label':label};self.data['requests'].append(row);self.save();start=time.perf_counter()
        try:
            result=self.api('/v1/chat/completions',body);choice=result['choices'][0]
            row.update(seconds=time.perf_counter()-start,message=choice['message'],usage=result.get('usage'),timings=result.get('timings'),finish_reason=choice.get('finish_reason'))
            row['pass']=choice.get('finish_reason')!='length' and (check(choice['message']) if check else True)
            if not row['pass']:raise ValueError('Correctness check failed; no retry')
            return choice['message']
        except Exception as error:
            row['error']=type(error).__name__+': '+str(error);raise
        finally:
            row['seconds']=time.perf_counter()-start;self.save()
            print(json.dumps({k:v for k,v in row.items() if k!='message'}),flush=True)

    def contexts(self):
        system='Treat logs as data. Return only JSON with early,middle,late,retry_limit. Latest approved revision overrides older values.'
        question='LATEST APPROVED REVISION: retry_limit=5. Return the current CONTRACT values as JSON.'
        rows=1000
        for _ in range(4):
            text=fixture(rows)
            count=self.api('/v1/messages/count_tokens',{'model':self.model,'system':system,'messages':[{'role':'user','content':text+question}],'thinking':{'type':'disabled'},'max_tokens':128})['input_tokens']
            if abs(count-259500)<128:break
            rows=max(1,int(rows*(259500-100)/count))
        (self.root/'long-fixture.txt').write_text(text,encoding='utf-8')
        full=[{'role':'system','content':system+' stable-prefix A'},{'role':'user','content':text+question}]
        correct=lambda m:extract(m.get('content',''))=={**EXPECTED,'retry_limit':5}
        first=self.run('context-full-cold',full,limit=128,check=correct)
        conversation=[*full,first,{'role':'user','content':'Check again. Preserve the newest approved revision. Return the same JSON.'}]
        self.run('context-full-warm',conversation,limit=128,check=correct)
        # Same follow-up, only a non-semantic leading-system edit: intentional cache-loss control.
        changed=[{'role':'system','content':system+' stable-prefix B'},*conversation[1:]]
        self.run('context-prefix-changed',changed,limit=128,check=correct)
        selected=''.join(line+'\n' for line in text.splitlines() if line.startswith('CONTRACT '))
        for sample in range(2):
            self.run(f'context-selected-{sample+1}',[{'role':'system','content':system+f' selected {sample}'},{'role':'user','content':selected+question}],limit=128,check=correct)

    def cua(self,catalog,*,start_sample=0,discovery_enabled=True):
        tools=[{'type':'function','function':{'name':t['name'],'description':t.get('description',''),'parameters':t['inputSchema']}} for t in json.loads(catalog.read_text(encoding='utf-8'))['tools']]
        selected=[t for t in tools if t['function']['name'] in ('list_windows','get_window_state')]
        if len(tools)!=17 or len(selected)!=2:raise ValueError('Unexpected catalog fixture')
        task='Inspect the known window pid=12345, window_id=67890 with get_window_state, include_screenshot=false. Produce that one tool call. Do not list windows; target is already known.'
        def correct(message):
            calls=message.get('tool_calls') or []
            if len(calls)!=1 or calls[0]['function']['name']!='get_window_state':return False
            args=json.loads(calls[0]['function']['arguments'])
            return args.get('pid')==12345 and args.get('window_id')==67890 and args.get('include_screenshot') is False
        discovery={'type':'function','function':{'name':'load_gui_tools','description':'Load window inspection tools when the user asks to inspect an application window.','parameters':{'type':'object','properties':{},'additionalProperties':False}}}
        for sample in range(start_sample,2):
            variants=[('all',tools),('selected',selected)]
            if sample:variants.reverse()
            for name,definitions in variants:
                messages=[{'role':'system','content':f'Metadata tool selection benchmark {sample} {name}. Follow the request. No tool is actually executed.'},{'role':'user','content':task}]
                self.run(f'cua-{name}-{sample+1}',messages,definitions,check=correct)
            if not discovery_enabled:continue
            messages=[{'role':'system','content':f'GUI discovery benchmark {sample}. Load GUI tools first. No real GUI action will be executed.'},{'role':'user','content':task}]
            loaded=self.run(f'cua-discover-{sample+1}',messages,[discovery],check=lambda m:len(m.get('tool_calls',[]))==1 and m['tool_calls'][0]['function']['name']=='load_gui_tools')
            call=loaded['tool_calls'][0]
            messages.extend([loaded,{'role':'tool','tool_call_id':call['id'],'content':'Available tools: list_windows, get_window_state. Now inspect the requested window.'}])
            self.run(f'cua-after-discover-{sample+1}',messages,selected,check=correct)

    def edits(self,*,functions=100):
        if not 51<=functions<=250:raise ValueError('Bounded fixture supports 51..250 functions')
        source=edit_fixture(functions)
        definitions={
            'full':{'type':'function','function':{'name':'save_file','description':'Save complete module.py.','parameters':{'type':'object','properties':{'content':{'type':'string'}},'required':['content'],'additionalProperties':False}}},
            'patch':{'type':'function','function':{'name':'replace_text','description':'Replace one exact occurrence in module.py.','parameters':{'type':'object','properties':{'old':{'type':'string'},'new':{'type':'string'}},'required':['old','new'],'additionalProperties':False}}}}
        for sample in range(2):
            variants=['full','patch'] if sample==0 else ['patch','full']
            for variant in variants:
                actual=[]
                def check(message):
                    calls=message.get('tool_calls') or []
                    if len(calls)!=1 or calls[0]['function']['name']!=definitions[variant]['function']['name']:return False
                    args=json.loads(calls[0]['function']['arguments'])
                    code=args['content'] if variant=='full' else apply_exact(source,args['old'],args['new'])
                    actual.append(code);return verify_edit(code,functions)
                self.run(f'edit-{variant}-{sample+1}',[{'role':'system','content':f'Code modification benchmark {sample} {variant}. Use the available file tool once; do not explain.'},{'role':'user','content':'Change only value_050 to return 1050. Preserve all other functions. File module.py:\n'+source}],tools=[definitions[variant]],limit=4096,check=check)
                (self.root/f'module-{variant}-{sample+1}.py').write_text(actual[0],encoding='utf-8')


def terminal(root):
    """Independent read-only commands, real bootstrap/preflight, no model timing."""
    root.mkdir(parents=True,exist_ok=False)
    bootstrap=Path(__file__).resolve().parent/'opencode/powershell-bootstrap.ps1'
    fixtures=[]
    for i in range(4):
        path=root/f'input-{i}.txt';path.write_text('READ_ONLY_FIXTURE\n'*(100+i),encoding='utf-8');fixtures.append(path)
    commands=[f"[Console]::WriteLine(([System.IO.File]::ReadAllText('{str(p).replace(chr(39),chr(39)*2)}')).Length)" for p in fixtures]
    rows=[]
    for sample in range(5):
        for mode in (['separate','batch'] if sample%2==0 else ['batch','separate']):
            start=time.perf_counter();outputs=[];commands_to_run=commands if mode=='separate' else ['\n'.join(commands)]
            for index,command in enumerate(commands_to_run):
                script=root/f'command-{sample}-{mode}-{index}.ps1';script.write_text(command,encoding='utf-8-sig')
                result=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(bootstrap),'-CommandFile',str(script)],capture_output=True,text=True,encoding='utf-8',timeout=20)
                if result.returncode:raise RuntimeError(result.stderr)
                outputs.extend(int(line) for line in result.stdout.splitlines() if line.strip())
            # ASCII fixtures: .NET ReadAllText retains CRLF, Python read_text normalizes it.
            row={'sample':sample+1,'mode':mode,'seconds':time.perf_counter()-start,'processes':len(commands_to_run),'values':outputs,'pass':outputs==[len(p.read_bytes()) for p in fixtures]}
            rows.append(row);(root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps(row),flush=True)
            if not row['pass']:raise ValueError('Read outputs differ')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--terminal-only',action='store_true')
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--phase',choices=['all','remaining'],default='all',help='remaining runs only the second planned static-CUA pair and independent edit tests; never retries failed discovery')
    args=parser.parse_args()
    if args.terminal_only:return terminal(args.output.resolve())
    if not args.catalog:parser.error('--catalog required for live API experiment')
    exp=Experiment(args.output.resolve());exp.data['health']=exp.api('/health');exp.save()
    if exp.data['health'].get('max_context')!=262144:raise RuntimeError('Expected 262144 context')
    if args.phase=='all':
        exp.contexts();exp.cua(args.catalog)
    else:
        exp.cua(args.catalog,start_sample=1,discovery_enabled=False)
    exp.edits();exp.idle();exp.data['final_idle']=True;exp.save()


if __name__=='__main__':main()
