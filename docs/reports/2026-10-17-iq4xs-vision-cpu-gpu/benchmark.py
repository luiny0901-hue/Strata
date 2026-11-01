from __future__ import annotations
import base64, json, os, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

scratch=Path(os.environ['STRATA_GPU_AB_SCRATCH'])
mode=sys.argv[1].lower(); device=sys.argv[2].lower()
assert mode in ('off','on') and device in ('cpu','gpu')
images=[]
for i in range(4):
    raw=(scratch/f'image-{i}.png').read_bytes()
    images.append('data:image/png;base64,'+base64.b64encode(raw).decode('ascii'))
parts=['Synthetic repository context only; these are prompt fixtures, not local or production source files.']
for module in range(1,13):
    parts.append(f'\n### src/Module{module:02d}/Service{module:02d}.cs\nnamespace Synthetic.Module{module:02d};\npublic sealed class Service{module:02d} : IService{module:02d}\n{{\n    private readonly IRecordStore _store;\n    private readonly IOperationJournal _journal;\n    private readonly IResourceLease _lease;\n')
    for method in range(1,9):
        n=module*100+method
        parts.append(f'''    public async Task<OperationResult> Execute{n:04d}Async(OperationRequest request, CancellationToken ct)
    {{
        var current = await _store.Read{method:02d}Async(request.Key, ct);
        if (current is null) return OperationResult.Missing(request.Key);
        var intent = await _journal.AppendIntentAsync(request.OperationId, "module-{module:02d}-{method:02d}", ct);
        if (!intent.Succeeded) return OperationResult.Reconciling(intent.EvidenceId);
        var updated = await _store.Prepare{method:02d}Async(current, request.Payload, ct);
        if (!updated.Succeeded) return OperationResult.Failed(updated.ErrorCode);
        var leaseResult = await _lease.Release{method:02d}Async(request.LeaseId, ct);
        if (!leaseResult.Succeeded) return OperationResult.PendingRelease(request.OperationId);
        return OperationResult.Accepted(request.OperationId, updated.Version);
    }}
''')
    parts.append('}\n')
context=''.join(parts)
base_prompt=(
    'You are reviewing a synthetic C# repository with many services. Read the supplied source excerpts '
    'and attached IDE screenshot. Identify the lifecycle persistence ordering defect in the visible '
    'StopAsync code, distinguish confirmed facts from assumptions, and provide exactly eight numbered '
    'regression tests plus a concise safe correction. Do not claim you ran code or changed files. Answer in Korean.\n\n'
    + context + '\n### Current file screenshot is attached below.\n'
)
url='http://127.0.0.1:18475/v1/chat/completions'
def send(label,image_index,limit):
    text=f'Request marker: {label:<12} image1920.\n'+base_prompt
    body={'model':'qwen3.8-flash-next-unsloth-ud-iq4_xs','messages':[
        {'role':'system','content':'Be a careful senior C# engineer. Use only supplied evidence and answer in Korean.'},
        {'role':'user','content':[{'type':'text','text':text},{'type':'image_url','image_url':{'url':images[image_index]}}]},
    ],'max_tokens':limit,'stream':False}
    req=urllib.request.Request(url,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST')
    started=datetime.now(timezone.utc).isoformat(); t0=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=900) as response:
            raw=response.read(); status=response.status
        out=json.loads(raw); choice=(out.get('choices') or [{}])[0]
        content=((choice.get('message') or {}).get('content') or '')
        return {'mode':mode,'vision':device,'label':label,'image_index':image_index,'started_utc':started,
                'wall_ms':round((time.perf_counter()-t0)*1000,1),'http_status':status,
                'usage':out.get('usage'),'timings':out.get('timings') or {},'finish_reason':choice.get('finish_reason'),
                'content_chars':len(content),'request_text_chars':len(text)}
    except Exception as e:
        status=getattr(e,'code',None)
        return {'mode':mode,'vision':device,'label':label,'image_index':image_index,'started_utc':started,
                'wall_ms':round((time.perf_counter()-t0)*1000,1),'http_status':status,
                'error':f'{type(e).__name__}: {e}','request_text_chars':len(text)}
rows=[{'kind':'warmup',**send('WARMUP0000',0,64)}]
for i in range(1,4):
    rows.append({'kind':'measured',**send(f'MEASURE{i:04d}',i,192)})
path=scratch/f'results-{mode}-{device}.json'
path.write_text(json.dumps({'prompt_chars':len(base_prompt),'mode':mode,'vision':device,'rows':rows},indent=2,ensure_ascii=False),encoding='utf-8')
for row in rows: print(json.dumps(row,ensure_ascii=False))
print('RESULT_FILE='+str(path))