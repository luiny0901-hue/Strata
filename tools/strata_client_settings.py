"""Project the existing Claude/Strata model policy into OpenCodex and Codex.

This is a setup-time projection, not another runtime configuration owner. MCP
processes, permissions, compaction and the agent loop still belong to each client.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
try:
    import tomllib
except ImportError:  # Do not break the existing Python 3.10 Claude-only doctor.
    tomllib = None

if __package__:
    from . import claude_opencodex_client as shared
    from .claude_code_guidance import language_reminder, validation_policy, scope_policy, CUA_INPUT_POLICY
    from .strata_anthropic_effort import EFFORT_LEVELS
else:
    import claude_opencodex_client as shared
    from claude_code_guidance import language_reminder, validation_policy, scope_policy, CUA_INPUT_POLICY
    from strata_anthropic_effort import EFFORT_LEVELS

MODEL_FIELDS = ('modelContextWindows', 'modelMaxOutputTokens',
                'modelReasoningEfforts', 'modelDefaultReasoningEfforts')
WIRE_HEADER = 'x-strata-effort-wire'
WIRE_VERSION = 'opencodex-low-medium-high-v1'
# The existing dispatcher permits 600-second calls. Give that owner time to
# return its timeout/cancellation result rather than cutting it off in Codex.
MCP_CALL_TIMEOUT_SECONDS = 660
# Startup has a 90-second outer limit. Three bounded 5-second metadata reads
# and at most three management calls must finish before that owner expires.
CONTEXT_SYNC_CALL_TIMEOUT_SECONDS = 20
MCP_START = '# BEGIN strata-client-mcp:v1'
MCP_END = '# END strata-client-mcp:v1'
GUIDE_START = '<!-- strata-client-guidance:v1 -->'
GUIDE_END = '<!-- /strata-client-guidance:v1 -->'


def _toml_loads(text):
    if tomllib is None:
        raise ValueError('Codex 설정 연결에는 Python 3.11 이상이 필요합니다.')
    return tomllib.loads(text)


def runtime_metadata(home, *, server_url=None, api_key_file=None, expected_model=None):
    """Read the READY local server, never a cached gateway model catalog.

    Endpoint/key overrides come only from the opted-in process owner. Do not
    follow redirects with credentials or copy the large template into receipts.
    """
    base, _ = shared.gateway(home)
    if server_url is not None or api_key_file is not None:
        parsed = urlsplit(server_url or '')
        if (parsed.scheme not in ('http', 'https')
                or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or api_key_file is None):
            raise ValueError('서버 소유자의 로컬 주소와 API 키 파일을 함께 지정하세요.')
        origin = server_url.rstrip('/')
        key = api_key_file.expanduser().read_text(encoding='utf-8-sig').strip()
        if not key or '\n' in key or '\r' in key:
            raise ValueError('서버 API 키 파일 형식을 확인하세요.')
        headers = {'Authorization': 'Bearer '+key}
    else:
        origin, headers = shared.strata_upstream(home)
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = build_opener(NoRedirect())
    def read(url, auth):
        try:
            with opener.open(Request(url, headers=auth), timeout=5) as response:
                raw = response.read(256*1024+1)
        except HTTPError as exc:
            exc.close()
            raise
        if len(raw) > 256*1024:
            raise ValueError('서버 정보가 256 KiB를 초과했습니다.')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('서버 정보는 JSON 객체여야 합니다.')
        return value
    gateway = read(base+'/healthz', {'Authorization': 'Bearer opencodex-proxy'})
    if gateway.get('status') != 'ok' or 'opencodex' not in str(gateway.get('service', '')).lower():
        raise ValueError('OpenCodex 상태를 확인할 수 없습니다.')
    health = read(origin+'/health', headers)
    model, context = health.get('model'), health.get('max_context')
    if (health.get('status') != 'ok' or health.get('loaded') is not True
            or health.get('service') != 'strata' or not isinstance(model, str)
            or not model.strip() or model != model.strip()
            or type(context) is not int or context < 4096):
        raise ValueError('실제 Strata 모델·컨텍스트가 준비되지 않았습니다.')
    if expected_model is not None and model != expected_model:
        raise ValueError('서버 소유자가 확인한 모델과 실제 모델이 다릅니다.')
    props = read(origin+'/props', headers)
    defaults = props.get('default_generation_settings', {})
    if props.get('model_alias') != model or defaults.get('n_ctx') != context:
        raise ValueError('조회 중 서버 모델 또는 컨텍스트가 바뀌었습니다. 새 상태를 확인하세요.')
    output = defaults.get('params', {}).get('n_predict', -1)
    if type(output) is not int or output == 0 or output < -1 or output >= context:
        raise ValueError('실제 서버 출력 기본값을 확인하세요.')
    if output == -1:
        output = shared.direct.context_limits(context)[0]
    result = {'model': model, 'context': context, 'max_output_tokens': output,
              'base_url': origin+'/v1', 'images': health.get('images') is True}
    if api_key_file is not None:
        # Keep an existing env/file reference when it resolves to the same key.
        # The editor already owns this field; changed keys never go to stdout.
        try:
            _, previous_headers = shared.strata_upstream(home)
        except (OSError, ValueError):
            previous_headers = {}
        if previous_headers.get('Authorization') != headers.get('Authorization'):
            result['api_key'] = key
    return result


def runtime_provider(provider, runtime):
    """Project only client-visible facts; engine/GPU/cache settings stay on the server."""
    result = deepcopy(provider)
    previous = result.get('defaultModel')
    model = runtime['model']
    result.update(defaultModel=model, baseUrl=runtime['base_url'])
    if 'api_key' in runtime:
        result['apiKey'] = runtime['api_key']
    if isinstance(result.get('models'), list):
        result['models'] = list(dict.fromkeys(model if m == previous else m for m in result['models']))
        if model not in result['models']:
            result['models'].append(model)
    capabilities = result.setdefault('modelCapabilities', {})
    if not isinstance(capabilities, dict) or not isinstance(capabilities.get(model, {}), dict):
        raise ValueError('Strata 모델 기능 설정은 JSON 객체여야 합니다.')
    capabilities.setdefault(model, {})['inputModalities'] = ['text', 'image'] if runtime['images'] else ['text']
    return result


def model_projection(provider, settings, context):
    """Keep other models, credentials and explicit request limits unchanged."""
    if type(context) is not int or context < 4096:
        raise ValueError('실제 Strata 컨텍스트 값을 확인하세요.')
    model = provider.get('defaultModel')
    if provider.get('adapter') != 'anthropic' or not isinstance(model, str) or not model:
        raise ValueError('현재 Strata Anthropic 공급자와 기본 모델을 먼저 확인하세요.')
    if settings.get('model') != 'strata/'+model:
        raise ValueError('Claude와 Strata 기본 모델이 다릅니다. 임의로 다른 모델 설정을 복사하지 않습니다.')
    output = settings.get('env', {}).get('CLAUDE_CODE_MAX_OUTPUT_TOKENS')
    if not isinstance(output, str) or not output.isascii() or not output.isdecimal():
        raise ValueError('Claude의 출력 토큰 설정이 유효하지 않습니다.')
    output = int(output)
    if not 1 <= output < context:
        raise ValueError('출력 토큰 설정은 실제 모델 컨텍스트보다 작아야 합니다.')
    effort = settings.get('effortLevel', 'medium')
    if effort not in EFFORT_LEVELS:
        raise ValueError('Claude 기본 추론 단계는 low, medium, high 중 하나여야 합니다.')
    result = deepcopy(provider)
    for field, value in zip(MODEL_FIELDS, (context, output, list(EFFORT_LEVELS), effort)):
        entries = result.setdefault(field, {})
        if not isinstance(entries, dict):
            raise ValueError(f'Strata {field} 형식을 확인하세요.')
        entries[model] = value
    headers = result.setdefault('headers', {})
    if not isinstance(headers, dict):
        raise ValueError('Strata headers 형식을 확인하세요.')
    # HTTP header names are case-insensitive; retain unrelated caller headers.
    for name in list(headers):
        if name.lower() == WIRE_HEADER:
            del headers[name]
    headers[WIRE_HEADER] = WIRE_VERSION
    return result


def sync_model(home, *, settings=None, context=None, timeout=60, runtime=None):
    """Use the live provider editor; never replace the full OpenCodex config."""
    base, model = shared.gateway(home)
    if runtime is not None and context is None:
        context = runtime['context']
    if context is None:
        context = shared.health(base, model, home=home, discover=False)
    path = home/'.opencodex/config.json'
    original = shared.read_json(path)['providers']['strata']
    if settings is None:
        settings = shared.read_json(home/'.claude/settings.json')
    projected = model_projection(runtime_provider(original, runtime) if runtime else original, settings, context)
    model = 'strata/'+projected['defaultModel']
    changed = projected != original
    backup = None
    if changed:
        # v2.92 has no max-output field in PATCH/models set. Its existing POST
        # provider editor supports it and publishes under the provider mutation lock.
        # Submit only the latest Strata provider, preserving all its other fields.
        if shared.read_json(path)['providers']['strata'] != original:
            raise ValueError('Strata 공급자가 변경됐습니다. 최신 상태에서 다시 확인하세요.')
        backup_dir = home/'.claude/backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile(prefix='strata-provider-', suffix='.json',
                                         dir=backup_dir, mode='w', encoding='utf-8', delete=False) as f:
            json.dump(original, f, ensure_ascii=False, indent=2)
            backup = f.name
        receipt, error = shared.management_json(home, base, '/api/providers',
            body={'name': 'strata', 'provider': projected}, timeout=timeout)
        if error or not isinstance(receipt, dict) or receipt.get('success') is not True:
            raise ValueError('OpenCodex 공급자 갱신이 확인되지 않았습니다. 자동 재전송하지 않습니다: '
                             +(error or 'invalid_receipt'))
    current = shared.read_json(path)['providers']['strata']
    if any(current.get(key) != projected.get(key) for key in
           (*MODEL_FIELDS, 'headers', 'defaultModel', 'baseUrl', 'apiKey', 'models', 'modelCapabilities')):
        raise ValueError('저장된 Strata 공통 설정이 요청한 값과 다릅니다.')
    return {'model': model, 'context': context,
            'max_output_tokens': projected['modelMaxOutputTokens'][model.split('/', 1)[1]],
            'reasoning_efforts': list(EFFORT_LEVELS),
            'default_effort': settings.get('effortLevel', 'medium'),
            'changed': changed, 'backup': backup, 'runtime_status': 'not_verified'}


def sync_desktop_context(home, base, model, *, timeout=60):
    """Refresh the applied gateway via OpenCodex's existing profile owner."""
    library = shared.desktop_config_library(home)
    meta = shared.read_json(library/'_meta.json', {})
    if not meta.get('appliedId'):
        return {'status': 'not_configured'}
    import uuid
    path = library/(str(uuid.UUID(meta['appliedId']))+'.json')
    profile = shared.read_json(path)
    if profile.get('inferenceProvider') != 'gateway' or profile.get('inferenceGatewayBaseUrl') != base:
        return {'status': 'another_profile_selected'}
    state, error = shared.management_json(home, base, '/api/claude-desktop', timeout=timeout)
    if error or not isinstance(state, dict):
        raise ValueError('Desktop 모델 프로필 조회 실패: '+str(error))
    row = next((r for r in state.get('rendered', []) if r.get('route') == model), None)
    if not row or not isinstance(row.get('name'), str):
        raise ValueError('현재 Desktop 프로필에서 Strata 경로를 찾지 못했습니다.')
    saved = next((r for r in profile.get('inferenceModels', []) if r.get('name') == row['name']), {})
    desired = row.get('supports1m') is True
    changed = not saved or bool(saved.get('supports1m')) != desired or bool(saved.get('prefer1m')) != desired
    if changed:
        mode = ('hybrid' if profile.get('inferenceModels') else 'discovery') if profile.get('modelDiscoveryEnabled') else 'static'
        receipt, error = shared.management_json(home, base, '/api/claude-desktop/apply',
                                               body={'mode': mode}, timeout=timeout)
        if error or not isinstance(receipt, dict) or receipt.get('applied') is not True:
            raise ValueError('Desktop 프로필 갱신이 확인되지 않았습니다: '+str(error))
        profile = shared.read_json(path)
        saved = next((r for r in profile.get('inferenceModels', []) if r.get('name') == row['name']), {})
        if not saved or bool(saved.get('supports1m')) != desired or bool(saved.get('prefer1m')) != desired:
            raise ValueError('저장된 Desktop 1M 표시가 실제 모델 정보와 다릅니다.')
    return {'status': 'new_desktop_session_required', 'wire_model': row['name'],
            'supports_1m': desired, 'changed': changed}


def sync_context(home, *, runtime=None):
    """Project the READY server's window through the existing client owners once.

    Sessions already open retain their own startup metadata. No client restart or
    request replay is performed here, and unrelated model selections are preserved.
    """
    base, previous_model = shared.gateway(home)
    context = runtime['context'] if runtime else shared.health(base, previous_model, home=home, discover=False)
    model = 'strata/'+runtime['model'] if runtime else previous_model
    profile = home/'.claude'
    path = profile/'settings.json'
    original = path.read_bytes()
    settings = json.loads(original)
    if not isinstance(settings, dict) or not isinstance(settings.get('env', {}), dict):
        raise ValueError('Claude settings/env는 JSON 객체여야 합니다.')
    claude_selected = settings.get('model') in (previous_model, model)
    if not claude_selected and runtime is None:
        raise ValueError('Claude의 선택 모델이 Strata와 다릅니다. 다른 모델 설정은 변경하지 않습니다.')
    provider = shared.read_json(home/'.opencodex/config.json')['providers']['strata']
    if not claude_selected:
        # Provider/catalog updates remain useful while Claude uses another model.
        # Build the Strata policy in memory without publishing foreign selections.
        settings['effortLevel'] = provider.get('modelDefaultReasoningEfforts', {}).get(
            runtime['model'], provider.get('modelDefaultReasoningEfforts', {}).get(
                previous_model.removeprefix('strata/'), 'medium'))
    output, window = shared.direct.context_limits(context)
    if runtime:
        output = runtime['max_output_tokens']
    env = settings.setdefault('env', {})
    env.update(CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(context),
               CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(output))
    if window == 'auto':
        env.pop('CLAUDE_CODE_AUTO_COMPACT_WINDOW', None)
    else:
        env['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] = str(window)
    # Managed aliases must follow a model rename, but explicit other model routes
    # are not selections this projection owns.
    for name in ('ANTHROPIC_MODEL', 'ANTHROPIC_SMALL_FAST_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL',
                 'ANTHROPIC_CUSTOM_MODEL_OPTION', 'ANTHROPIC_DEFAULT_OPUS_MODEL',
                 'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL'):
        if env.get(name) == previous_model:
            env[name] = model
    settings.update(model=model, autoCompactWindow=window, autoCompactEnabled=True)
    # An explicit disable would otherwise silently defeat the requested window.
    for name in ('DISABLE_AUTO_COMPACT', 'DISABLE_COMPACT', 'CLAUDE_CODE_DISABLE_1M_CONTEXT'):
        env.pop(name, None)
    files = {path: json.dumps(settings, ensure_ascii=False, indent=2)+'\n'} if claude_selected else {}
    before = {path: original} if claude_selected else {}
    state_path = profile/shared.STATE
    if state_path.is_file():
        before[state_path] = state_path.read_bytes()
        state = json.loads(before[state_path])
        state.update(context=context, model=model)
        files[state_path] = json.dumps(state, ensure_ascii=False, indent=2)+'\n'
    # An existing per-model Codex catalog must agree. Never set a global override:
    # the user also selects other models and those keep their own windows.
    codex_config = home/'.codex/config.toml'
    codex = _toml_loads(codex_config.read_text(encoding='utf-8')) if codex_config.is_file() else {}
    if codex.get('model_catalog_json') and (codex.get('model_context_window', context) != context
            or codex.get('model_auto_compact_token_limit') is not None):
        raise ValueError('Codex 전역 컨텍스트/압축 설정이 모델별 동기화와 충돌합니다. 기존 값은 보존했습니다.')
    # Validate the complete projection before touching any owner. Publish local
    # files last: a refused/uncertain remote write must not advance Claude alone.
    model_projection(runtime_provider(provider, runtime) if runtime else provider, settings, context)
    phase = 'provider'
    try:
        result = sync_model(home, settings=settings, context=context,
                            timeout=CONTEXT_SYNC_CALL_TIMEOUT_SECONDS, runtime=runtime)
        phase = 'codex_catalog'
        saved = audit(home)
        if codex.get('model_catalog_json') and (not saved['checks']['codex_context']
                or not saved['checks']['codex_auto_compaction']
                or saved['codex_global_compaction_override'] is not None):
            raise ValueError('Codex 카탈로그/압축 기준이 서버 한도와 다릅니다.')
        phase = 'desktop'
        desktop = sync_desktop_context(home, base, model, timeout=CONTEXT_SYNC_CALL_TIMEOUT_SECONDS)
        phase = 'local_settings'
        backup, changed = shared.publish_files(files, profile, before)
    except (OSError, ValueError, RuntimeError) as exc:
        # Other owners may already have accepted their updates. Do not roll them
        # back or replay uncertain requests; retain the provider owner's backup.
        raise ValueError(f'컨텍스트 동기화 중단: context={context}, phase={phase}. '
                         '일부 원격 설정은 반영됐을 수 있으므로 현재 상태를 확인하세요. '
                         '자동 재전송하지 않습니다. '+str(exc)) from exc
    return {**result, 'claude_compaction_window': window,
            'server': {'base_url': runtime['base_url'], 'images': runtime['images']} if runtime else None,
            'desktop': desktop,
            'codex_compaction_trigger': saved['codex_compaction_trigger'],
            'settings_changed_files': changed, 'settings_backup': str(backup) if backup else None,
            'claude_selection': 'synchronized' if claude_selected else 'another_model_preserved',
            'runtime_status': 'new_client_session_required'}


def sync_runtime(home, **kwargs):
    """One snapshot and one projection per opted-in start/restart; no watcher."""
    return sync_context(home, runtime=runtime_metadata(home, **kwargs))


def _toml_server(name, server):
    if (not isinstance(server, dict) or server.get('type', 'stdio') != 'stdio'
            or not isinstance(server.get('command'), str) or not server['command']
            or not isinstance(server.get('args', []), list)
            or not all(isinstance(arg, str) for arg in server.get('args', []))
            or not isinstance(server.get('env', {}), dict)
            or not all(isinstance(k, str) and isinstance(v, str)
                       for k, v in server.get('env', {}).items())):
        raise ValueError(f'{name}의 stdio MCP 실행 설정을 확인하세요.')
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    body = f'[mcp_servers.{quote(name)}]\ncommand = {quote(server["command"])}\n'
    body += 'args = '+quote(server.get('args', []))+'\n'
    body += f'tool_timeout_sec = {MCP_CALL_TIMEOUT_SECONDS}\n'
    if server.get('enabled') is False:
        body += 'enabled = false\n'
    if server.get('env'):
        body += f'\n[mcp_servers.{quote(name)}.env]\n'
        body += ''.join(f'{quote(k)} = {quote(v)}\n' for k, v in server['env'].items())
    return MCP_START+'\n'+body+MCP_END+'\n'


def _merge_block(text, block, start, end, *, prior_hash=None):
    """Preserve user text and refuse edited, duplicate or incomplete owned blocks."""
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise ValueError('공통 설정의 관리 블록이 불완전하거나 중복되었습니다.')
    if start not in text:
        return text+('' if not text or text.endswith('\n') else '\n')+'\n'+block
    first = text.index(start)
    last = text.index(end, first)+len(end)
    if text[last:last+1] == '\n':
        last += 1
    existing = text[first:last]
    if existing != block and (not prior_hash or hashlib.sha256(existing.encode()).hexdigest() != prior_hash):
        raise ValueError('사용자가 수정한 공통 설정 블록을 보존합니다.')
    return text[:first]+block+text[last:]


def _codex_guide():
    root = shared.ROOT
    return (GUIDE_START+'\n'+language_reminder()+'\n\n'
        '실제 실행·도구·압축·취소·완료는 현재 클라이언트가 소유한다. Claude 전용 훅·완료 도구를 호출한 척하지 않는다. '
        '프로젝트 AGENTS.md와 기존 코드·빌드 절차를 우선한다. 구현·설계·창작의 공통 기준이 현재 문맥에 없을 때만 '
        f'`{(root/"examples/claude/KOREAN_INSTRUCTIONS.md").as_posix()}`의 공통 요청 해석·산출물 형태·품질·보고 기준을 처음 한 번 읽는다. '
        '이미 제공되거나 읽은 지침은 재사용하고, 같은 대화의 작은 수정마다 다시 읽지 않는다. 지침 변경·새 요구·압축 후 불확실성이 있으면 관련 절만 확인한다. '
        '도구 이름·세션 기능은 해당 문서의 Claude 예시를 복제하지 않고 현재 제공된 도구를 사용한다. '
        '복잡한 개발·재설계·장기 유지보수에서만 '
        f'`{(root/"examples/claude/STRATA_SESSION_RECOVERY_KO.md").as_posix()}`의 '
        '현재 상태·변경·검증 및 장기 개발·유지보수 기준을 읽는다. 상세 엔진/데스크톱 지침은 '
        f'`{(root/"examples/claude/game-engines").as_posix()}` 또는 '
        f'`{(root/"examples/claude/professional").as_posix()}`에서 해당 대상 하나만 읽는다.\n\n'
        +scope_policy(root)+'\n\n'+validation_policy(root)+'\n\n'+
        'GUI·역분석·웹 검색이 필요할 때만 agent-tools의 검색으로 필요한 하위 도구를 찾고 반환된 정확한 이름·스키마로 호출한다. '
        +CUA_INPUT_POLICY+' '+
        'MCP 등록은 도구 실행 성공이나 승인·현재 세션 연결을 증명하지 않는다.\n'+GUIDE_END+'\n')


def sync_codex(home):
    """Share only lazy MCP and guidance; do not change selected model or permissions."""
    profile = home/'.codex'
    state_path = profile/'strata-clients.json'
    state = shared.read_json(state_path, {})
    native = shared.read_json(home/'.claude.json')
    agent = native.get('mcpServers', {}).get('agent-tools')
    if not agent:
        raise ValueError('Claude의 기존 agent-tools 연결을 먼저 설정하세요.')
    specs = [(profile/'config.toml', 'agent-tools', agent)]
    owner = shared.read_json(home/'.claude'/shared.STATE, {}).get('maintenance_mcp', {})
    project = owner.get('project')
    if project:
        project_settings = native.get('projects', {}).get(project, {})
        server = project_settings.get('mcpServers', {}).get('strata-maintenance')
        if not server:
            raise ValueError('기존 유지보수 MCP의 프로젝트 소유 설정을 확인하세요.')
        if 'strata-maintenance' in project_settings.get('disabledMcpServers', []):
            server = {**server, 'enabled': False}
        specs.append((Path(project)/'.codex/config.toml', 'strata-maintenance', server))
    files, before, hashes = {}, {}, {}
    for path, name, server in specs:
        raw = path.read_bytes() if path.exists() else None
        text = raw.decode('utf-8') if raw is not None else ''
        parsed = _toml_loads(text)
        existing = parsed.get('mcp_servers', {}).get(name)
        block = _toml_server(name, server)
        expected = _toml_loads(block)['mcp_servers'][name]
        if existing is not None and MCP_START not in text:
            # A user-owned equivalent registration needs no adoption/rewriting.
            if existing != expected:
                raise ValueError(f'기존 Codex {name} 설정이 다릅니다. 덮어쓰지 않습니다.')
            continue
        key = str(path.resolve())
        updated = _merge_block(text, block, MCP_START, MCP_END,
                               prior_hash=state.get('blocks', {}).get(key))
        _toml_loads(updated)
        files[path], before[path] = updated, raw
        hashes[key] = hashlib.sha256(block.encode()).hexdigest()
    path = profile/'AGENTS.md'
    raw = path.read_bytes() if path.exists() else None
    guide = _codex_guide()
    files[path] = _merge_block(raw.decode('utf-8') if raw is not None else '', guide,
                              GUIDE_START, GUIDE_END, prior_hash=state.get('guidance_sha256'))
    before[path] = raw
    before[state_path] = state_path.read_bytes() if state_path.exists() else None
    files[state_path] = json.dumps({'version': 1, 'blocks': hashes,
        'guidance_sha256': hashlib.sha256(guide.encode()).hexdigest()}, indent=2)+'\n'
    backup, changed = shared.publish_files(files, profile, before)
    return {'changed_files': changed, 'backup': str(backup) if backup else None,
            'mcp': ['agent-tools'], 'maintenance_project': project,
            'runtime_status': 'restart_client_required'}


def audit(home):
    """Read saved projections only. No catalog refresh, server or model requests."""
    provider = shared.read_json(home/'.opencodex/config.json', {}).get('providers', {}).get('strata', {})
    model_id = provider.get('defaultModel')
    model = 'strata/'+model_id if isinstance(model_id, str) else None
    settings = shared.read_json(home/'.claude/settings.json', {})
    native = shared.read_json(home/'.claude.json', {})
    env = settings.get('env', {})
    context = provider.get('modelContextWindows', {}).get(model_id)
    output = provider.get('modelMaxOutputTokens', {}).get(model_id)
    codex_path = home/'.codex/config.toml'
    codex = _toml_loads(codex_path.read_text(encoding='utf-8')) if codex_path.is_file() else {}
    catalog_path = codex.get('model_catalog_json')
    catalog = shared.read_json(Path(catalog_path).expanduser(), {}) if isinstance(catalog_path, str) else {}
    rows = catalog if isinstance(catalog, list) else catalog.get('models', [])
    row = next((r for r in rows if isinstance(r, dict) and r.get('slug') == model), {})
    levels = [r.get('effort') for r in row.get('supported_reasoning_levels', []) if isinstance(r, dict)]
    window, source = shared.saved_compaction_window(settings, model, context or 262144)
    effective_codex_context = codex.get('model_context_window', row.get('context_window'))
    def native_server(name):
        entry = codex.get('mcp_servers', {}).get(name)
        expected = native.get('mcpServers', {}).get(name)
        return (isinstance(entry, dict) and isinstance(expected, dict)
                and entry.get('enabled') is not False
                and all(entry.get(k, default) == expected.get(k, default)
                        for k, default in [('command', None), ('args', []), ('env', {})]))
    checks = {
        'claude_model': settings.get('model') == model,
        'claude_context': context is not None and env.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS') == str(context),
        'claude_output': output is not None and env.get('CLAUDE_CODE_MAX_OUTPUT_TOKENS') == str(output),
        'codex_context': bool(row) and effective_codex_context == context,
        'codex_auto_compaction': (type(row.get('auto_compact_token_limit')) is int
            and type(effective_codex_context) is int
            and 0 < row['auto_compact_token_limit'] < effective_codex_context),
        'native_efforts': provider.get('modelReasoningEfforts', {}).get(model_id) == list(EFFORT_LEVELS),
        'default_effort': provider.get('modelDefaultReasoningEfforts', {}).get(model_id) == settings.get('effortLevel'),
        'effort_wire': any(k.lower() == WIRE_HEADER and v == WIRE_VERSION
                           for k, v in provider.get('headers', {}).items()),
        'codex_agent_tools': native_server('agent-tools'),
        'codex_mcp_call_timeout': codex.get('mcp_servers', {}).get('agent-tools', {}).get('tool_timeout_sec', 60) >= 600,
    }
    return {'checks': checks, 'configured': all(checks.values()), 'model': model,
        'context': context, 'default_max_output_tokens': output,
        'native_efforts': provider.get('modelReasoningEfforts', {}).get(model_id),
        'codex_advertised_efforts': levels,
        'codex_gateway_only_efforts': [v for v in levels if v not in EFFORT_LEVELS],
        'claude_compaction_window': window, 'claude_compaction_source': source,
        'codex_compaction_trigger': row.get('auto_compact_token_limit'),
        'codex_effective_context': effective_codex_context,
        'codex_global_context_override': codex.get('model_context_window'),
        'codex_global_compaction_override': codex.get('model_auto_compact_token_limit'),
        'runtime_status': 'not_verified',
        'scope': 'Saved model/MCP projections only. Client compaction, prompts, permissions and current UI selection are independent.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', action='store_true', help='Codex의 지연 MCP·한국어 지침도 연결')
    parser.add_argument('--codex-only', action='store_true',
                        help='다른 PC에서 공통 모델 설정은 건드리지 않고 로컬 Codex MCP·지침만 연결')
    parser.add_argument('--check', action='store_true', help='변경 없이 저장된 클라이언트 설정 차이 확인')
    parser.add_argument('--sync-context', action='store_true', help='준비된 서버의 컨텍스트·압축 창만 동기화')
    parser.add_argument('--sync-runtime', action='store_true', help='준비된 서버의 모델·컨텍스트·출력·비전 정보를 동기화')
    parser.add_argument('--server-url', help='관리 실행기가 소유한 로컬 Strata 주소')
    parser.add_argument('--api-key-file', type=Path, help='해당 서버의 기존 API 키 파일')
    parser.add_argument('--expected-model', help='관리 실행기가 READY에서 확인한 모델 ID')
    args = parser.parse_args(argv)
    home = Path.home()
    if args.sync_runtime:
        print(json.dumps(sync_runtime(home, server_url=args.server_url,
                                    api_key_file=args.api_key_file, expected_model=args.expected_model),
                         ensure_ascii=False))
        return 0
    if args.server_url or args.api_key_file or args.expected_model:
        parser.error('서버 식별 인수는 --sync-runtime과 함께 사용하세요.')
    if args.sync_context:
        print(json.dumps(sync_context(home), ensure_ascii=False))
        return 0
    if args.check:
        result = audit(home)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['configured'] else 1
    result = {} if args.codex_only else {'shared_model': sync_model(home)}
    if args.codex or args.codex_only:
        result['codex'] = sync_codex(home)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
