"""Portable Strata preferences; executable paths and provider credentials are rebuilt locally."""
import json
from pathlib import Path

LEVELS = ('none','low','medium','high')
BODY_KEYS = ('temperature','top_p','top_k','reasoning_effort')

def export_profile(config, home, effort=None):
    selected=config.get('model','')
    provider,_,model=selected.partition('/') if isinstance(selected,str) else ('','','')
    body=config.get('providers',{}).get(provider,{}).get('models',{}).get(model,{}).get('body',{})
    result={'version':1,'build_steps':config.get('agents',{}).get('build',{}).get('steps',200),
            'compaction':config.get('compaction',{}),
            'body':{k:v for k,v in body.items() if k in BODY_KEYS},
            'tools':{k:v for k,v in config.get('tools',{}).items() if isinstance(v,bool)},'instructions':[]}
    if effort in LEVELS:result['body']['reasoning_effort']=effort
    for name in config.get('instructions',[]):
        if not isinstance(name,str):continue
        path=Path(str(home)+name[1:]) if name.startswith('~/') else Path(name)
        if path.is_file():
            text=path.read_text(encoding='utf-8-sig')
            if text not in result['instructions']:result['instructions'].append(text)
    validate(result)
    return result

def validate(profile):
    if not isinstance(profile,dict) or profile.get('version')!=1:raise ValueError('지원하지 않는 설정 백업입니다.')
    steps=profile.get('build_steps')
    if type(steps)!=int or not 1<=steps<=10000:raise ValueError('작업 단계 제한이 잘못됐습니다.')
    body=profile.get('body',{})
    if not isinstance(body,dict) or set(body)-set(BODY_KEYS):raise ValueError('모델 설정 항목이 잘못됐습니다.')
    for key,value in body.items():
        if key=='reasoning_effort':
            if value not in LEVELS:raise ValueError('추론 강도가 잘못됐습니다.')
        elif type(value) not in (int,float):raise ValueError('샘플링 값이 잘못됐습니다.')
    tools=profile.get('tools',{})
    if not isinstance(tools,dict) or any(not isinstance(k,str) or type(v)!=bool for k,v in tools.items()):raise ValueError('도구 설정이 잘못됐습니다.')
    instructions=profile.get('instructions',[])
    if not isinstance(instructions,list) or any(not isinstance(x,str) for x in instructions) or sum(map(len,instructions))>1048576:raise ValueError('지침 백업 크기나 형식이 잘못됐습니다.')
    compaction=profile.get('compaction',{})
    if not isinstance(compaction,dict):raise ValueError('압축 설정이 잘못됐습니다.')
    if set(compaction)-{'auto','keep','buffer'}:raise ValueError('지원하지 않는 압축 설정입니다.')
    if 'auto' in compaction and type(compaction['auto'])!=bool:raise ValueError('압축 자동 설정이 잘못됐습니다.')
    for value in [compaction.get('buffer',0),compaction.get('keep',{}).get('tokens',0) if isinstance(compaction.get('keep',{}),dict) else -1]:
        if type(value)!=int or value<0:raise ValueError('압축 토큰 설정이 잘못됐습니다.')
    return profile

def apply_profile(config, profile):
    validate(profile)
    config.setdefault('agents',{}).setdefault('build',{})['steps']=profile['build_steps']
    model=config['providers']['strata']['models']['server']
    model.setdefault('body',{}).update(profile.get('body',{}))
    config.setdefault('tools',{}).update(profile.get('tools',{}))
    # Preserve server-derived limits when the destination has a smaller context.
    context=model['limit']['context'];available=max(1,context-model['limit']['output'])
    requested=profile.get('compaction',{});target=config['compaction']
    if 'auto' in requested:target['auto']=requested['auto']
    if 'buffer' in requested:target['buffer']=min(requested['buffer'],available//2)
    if 'keep' in requested:target['keep']={'tokens':min(requested['keep'].get('tokens',0),max(0,available-target.get('buffer',0)))}
    return '\n\n'.join(profile.get('instructions',[]))
