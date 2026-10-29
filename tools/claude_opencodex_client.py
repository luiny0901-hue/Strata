"""Opt-in shared Claude Code CLI/IDE setup for an existing OpenCodex gateway."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from statistics import median
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from urllib.error import HTTPError

if __package__:
    from . import claude_code_support as direct
    from . import claude_mcp_config as mcp_config_module
    from .claude_mcp import searxng_search
else:
    import claude_code_support as direct
    import claude_mcp_config as mcp_config_module
    from claude_mcp import searxng_search


STATE = 'strata-opencodex.json'
MCP_SOURCE = 'strata-mcp.json'
ROOT = Path(__file__).resolve().parents[1]
MODEL_CATALOG_TIMEOUT_SECONDS = 15


def _physical_memory_bytes():
    """Read total and currently available physical memory without extra packages."""
    if os.name == 'nt':
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError('GlobalMemoryStatusEx failed')
        return int(status.ullTotalPhys), int(status.ullAvailPhys)

    if sys.platform.startswith('linux'):
        values = {}
        with open('/proc/meminfo', encoding='ascii') as stream:
            for line in stream:
                key, _, rest = line.partition(':')
                if key in ('MemTotal', 'MemAvailable'):
                    fields = rest.split()
                    if len(fields) >= 2 and fields[1] == 'kB' and fields[0].isascii() and fields[0].isdecimal():
                        values[key] = int(fields[0])*1024
        if 'MemTotal' in values and 'MemAvailable' in values:
            return values['MemTotal'], values['MemAvailable']

    page_size = os.sysconf('SC_PAGE_SIZE')
    total_pages = os.sysconf('SC_PHYS_PAGES')
    available_pages = os.sysconf('SC_AVPHYS_PAGES')
    return int(page_size)*int(total_pages), int(page_size)*int(available_pages)


def host_memory_status():
    """Return a bounded physical-memory snapshot, not a workload admission test."""
    scope = ('현재 물리 메모리 여유량의 순간 관측입니다. GPU 메모리·프로세스별 사용량·모델의 추가 메모리 요구량을 '
             '측정하지 않으며, 대용량 작업의 안전 실행을 보장하지 않습니다.')
    try:
        total, available = _physical_memory_bytes()
        if (type(total) is not int or type(available) is not int
                or total <= 0 or available < 0 or available > total):
            return {'status': 'unavailable', 'reason': 'invalid_memory_status', 'scope': scope}
        mib = 1024*1024
        return {'status': 'observed', 'total_mib': round(total/mib),
                'available_mib': round(available/mib),
                'available_percent': round(available*100/total, 1), 'scope': scope}
    except (OSError, AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return {'status': 'unavailable', 'reason': 'host_memory_unavailable', 'scope': scope}


def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'JSON 객체가 필요합니다: {path}')
    return value


def gateway(home):
    config = read_json(home/'.opencodex/config.json')
    port = config.get('port', 10100)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('OpenCodex 포트 형식을 확인하세요.')
    provider = config.get('providers', {}).get('strata', {})
    model = provider.get('defaultModel')
    if not isinstance(model, str) or not model:
        raise ValueError('OpenCodex의 Strata 기본 모델을 먼저 선택하세요.')
    return f'http://127.0.0.1:{port}', f'strata/{model}'


def strata_upstream(home=None):
    """Return the validated local Strata origin and its existing credential."""
    config = read_json((home or Path.home())/'.opencodex/config.json')
    provider = config.get('providers', {}).get('strata', {})
    parsed = urlsplit(provider.get('baseUrl', ''))
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip('/') not in ('', '/v1')):
        raise ValueError('OpenCodex의 Strata 공급자 주소 형식을 확인하세요.')
    # This local maintenance integration never sends the provider credential elsewhere.
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('이 유지보수 연결은 로컬 Strata 공급자만 지원합니다.')
    key = provider.get('apiKey', '')
    if not isinstance(key, str):
        raise ValueError('Strata 공급자 인증 형식을 확인하세요.')
    if key.startswith('{file:') and key.endswith('}'):
        key = Path(key[6:-1]).expanduser().read_text(encoding='utf-8-sig').strip()
    elif key.startswith('{env:') and key.endswith('}'):
        key = os.environ.get(key[5:-1], '')
    origin = f'{parsed.scheme}://{parsed.netloc}'
    return origin, {'Authorization': 'Bearer '+key} if key else {}


def health(base, model, *, home=None, discover=True):
    headers = {'Authorization': 'Bearer opencodex-proxy'}
    with urlopen(Request(base+'/healthz', headers=headers), timeout=5) as response:
        status = json.load(response)
    if status.get('status') != 'ok' or 'opencodex' not in status.get('service', '').lower():
        raise ValueError('해당 주소에서 OpenCodex 상태를 확인할 수 없습니다.')
    context = None
    if discover:
        # OpenCodex may refresh several provider catalogs on the first request. A
        # local live catalog request was observed taking ~8.5s, so a 5s timeout
        # incorrectly reports a healthy gateway as unavailable during setup.
        with urlopen(Request(base+'/v1/models', headers=headers), timeout=MODEL_CATALOG_TIMEOUT_SECONDS) as response:
            models = json.load(response).get('data', [])
        row = next((row for row in models if row.get('id') == model), None)
        if row is None:
            raise ValueError('OpenCodex에서 Strata 모델을 조회할 수 없습니다. 서버와 공급자 설정을 확인하세요.')
        context = row.get('context_window')
        if type(context) is not int or context < 4096:
            raise ValueError('조회된 Strata 컨텍스트 크기를 확인할 수 없습니다.')
    # Catalog discovery may be cached even while the actual inference process is down.
    origin, upstream_headers = strata_upstream(home)
    # Do not follow an upstream redirect with its credentials.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(origin+'/health', headers=upstream_headers), timeout=5) as response:
            upstream = json.load(response)
    except HTTPError as exc:
        exc.close()
        raise
    if (upstream.get('status') != 'ok' or upstream.get('loaded') is not True
            or upstream.get('model') != model.removeprefix('strata/')):
        raise ValueError('실제 Strata 모델이 준비되지 않았거나 모델 ID가 다릅니다.')
    actual = upstream.get('max_context')
    if type(actual) is not int or actual < 4096:
        raise ValueError('실제 Strata 컨텍스트 크기를 확인할 수 없습니다.')
    return min(context, actual) if context is not None else actual


def _bounded_status_number(value, *, minimum=0, maximum=1_000_000, digits=1):
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        return None
    if digits == 0:
        return int(round(value))
    return round(value, digits) if type(value) is float else value


def _sanitized_gpu(value):
    if not isinstance(value, dict):
        return None
    row = {}
    name = value.get('name')
    if isinstance(name, str) and name.strip() and len(name) <= 128 and not any(ord(c) < 32 for c in name):
        row['name'] = name.strip()
    for key in ('used_mib', 'total_mib'):
        number = _bounded_status_number(value.get(key), maximum=10_000_000, digits=0)
        if number is not None:
            row[key] = number
    if ('used_mib' in row and 'total_mib' in row
            and row['used_mib'] > row['total_mib']):
        row.pop('used_mib')
    for key, maximum, digits in (('util_pct', 100, 1), ('temp_c', 150, 1), ('power_w', 2000, 1)):
        number = _bounded_status_number(value.get(key), minimum=-40 if key == 'temp_c' else 0,
                                        maximum=maximum, digits=digits)
        if number is not None:
            row[key] = number
    for key in ('index',):
        number = _bounded_status_number(value.get(key), maximum=255, digits=0)
        if number is not None:
            row[key] = number
    role = value.get('role')
    if isinstance(role, str) and role in ('model', 'unused', 'vision', 'shared'):
        row['role'] = role
    return row or None


def strata_runtime_status(home=None, *, timeout=2):
    """Read bounded, sanitized telemetry from the authenticated local Strata status API."""
    scope = ('Strata의 로컬 상태 API에서 읽은 순간 관측입니다. GPU 메모리는 다른 앱과 공유되는 장치 전체 값이며 '
             '작업별 메모리 요구량이나 실행 가능성을 보장하지 않습니다. 활성 요청은 Strata에 전달된 요청만 포함하고 '
             'OpenCodex에서 아직 전달되지 않은 대기열은 포함하지 않습니다.')
    unknown = {'status': 'unknown', 'reason': 'strata_status_unavailable', 'scope': scope}
    try:
        origin, headers = strata_upstream(home)
        request = Request(origin+'/v1/status', headers=headers)
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(256*1024+1)
        if len(raw) > 256*1024:
            return {**unknown, 'reason': 'response_too_large'}
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('service') != 'strata':
            return {**unknown, 'reason': 'invalid_status_response'}

        result = {'status': 'observed', 'scope': scope}
        if type(data.get('loaded')) is bool:
            result['loaded'] = data['loaded']
        context = _bounded_status_number(data.get('cache_max_tokens'), minimum=4096,
                                         maximum=10_000_000, digits=0)
        if context is not None:
            result['context_tokens'] = context
        concurrency = data.get('concurrency')
        if isinstance(concurrency, dict):
            serving = _bounded_status_number(concurrency.get('serving'), minimum=1, maximum=1024, digits=0)
            requested = _bounded_status_number(concurrency.get('requested'), minimum=1, maximum=1024, digits=0)
            if serving is not None or requested is not None:
                result['concurrency'] = {key: value for key, value in
                    (('serving', serving), ('requested', requested)) if value is not None}
        activity = data.get('activity')
        if isinstance(activity, dict):
            in_flight = _bounded_status_number(activity.get('in_flight'), maximum=1_000_000, digits=0)
            requests = _bounded_status_number(activity.get('requests'), maximum=1_000_000_000, digits=0)
            result['activity'] = {'status': 'idle' if in_flight == 0 else 'busy' if in_flight is not None else 'unknown',
                                  'is_idle': in_flight == 0 if in_flight is not None else None,
                                  'in_flight': in_flight}
            if requests is not None:
                result['activity']['requests'] = requests
            last_request_at = _bounded_status_number(activity.get('last_request_at'), maximum=4_102_444_800,
                                                     digits=0)
            if last_request_at is not None:
                result['activity']['last_request_at'] = last_request_at

        timings = data.get('last_timings')
        if isinstance(timings, dict):
            safe_timings = {}
            for key in ('prompt_n', 'predicted_n', 'cache_n', 'draft_n', 'draft_n_accepted'):
                number = _bounded_status_number(timings.get(key), maximum=10_000_000, digits=0)
                if number is not None:
                    safe_timings[key] = number
            for key in ('prompt_per_second', 'predicted_per_second'):
                number = _bounded_status_number(timings.get(key), maximum=1_000_000, digits=1)
                if number is not None:
                    safe_timings[key] = number
            for key in ('prompt_ms', 'predicted_ms', 'predicted_per_token_ms'):
                number = _bounded_status_number(timings.get(key), maximum=3_600_000, digits=1)
                if number is not None:
                    safe_timings[key] = number
            if safe_timings:
                result['last_request_timings'] = safe_timings

        machine = data.get('machine')
        if isinstance(machine, dict):
            safe_machine = {}
            gpu = _sanitized_gpu(machine.get('gpu'))
            if gpu:
                safe_machine['gpu'] = gpu
            gpus = machine.get('gpus')
            if isinstance(gpus, list):
                safe_gpus = []
                for index, candidate in enumerate(gpus[:8]):
                    sanitized = _sanitized_gpu(candidate)
                    if sanitized:
                        sanitized.setdefault('index', index)
                        safe_gpus.append(sanitized)
                if safe_gpus:
                    safe_machine['gpus'] = safe_gpus
            ram = machine.get('ram')
            if isinstance(ram, dict):
                safe_ram = {}
                for key in ('used_gib', 'total_gib'):
                    number = _bounded_status_number(ram.get(key), maximum=1_000_000, digits=1)
                    if number is not None:
                        safe_ram[key] = number
                if 'used_gib' in safe_ram and 'total_gib' in safe_ram and safe_ram['used_gib'] > safe_ram['total_gib']:
                    safe_ram.pop('used_gib')
                if safe_ram:
                    safe_machine['ram'] = safe_ram
            if safe_machine:
                result['machine'] = safe_machine
        vram = data.get('vram')
        if isinstance(vram, dict) and type(vram.get('elastic')) is bool:
            result['vram'] = {'elastic': vram['elastic']}
        return result
    except HTTPError as exc:
        exc.close()
        return {**unknown, 'reason': 'HTTPError'}
    except Exception as exc:
        return {**unknown, 'reason': type(exc).__name__}


def strata_activity(home=None, *, timeout=3, runtime_status=None):
    """Read active Strata work; OpenCodex requests not yet submitted are outside this observation."""
    scope = ('Strata 실행 슬롯만 조회합니다. OpenCodex 대기열이나 아직 Strata에 전달되지 않은 요청은 '
             '포함하지 않으므로 전체 경로의 유휴 상태를 단독으로 증명하지 않습니다.')
    started = time.monotonic()
    if runtime_status is None:
        runtime_status = strata_runtime_status(home, timeout=min(timeout, 1))
    activity = runtime_status.get('activity') if isinstance(runtime_status, dict) else None
    if isinstance(activity, dict) and activity.get('status') in ('idle', 'busy'):
        return {'status': activity['status'], 'is_idle': activity['is_idle'],
                'in_flight': activity.get('in_flight'), 'scope': scope}
    try:
        origin, headers = strata_upstream(home)
        from urllib.request import HTTPRedirectHandler, build_opener
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        request = Request(origin+'/slots', headers=headers)
        remaining = max(0.2, timeout-(time.monotonic()-started))
        with build_opener(NoRedirect()).open(request, timeout=remaining) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return {'status': 'unknown', 'is_idle': None, 'scope': scope,
                    'reason': 'response_too_large'}
        slots = json.loads(raw)
        if (not isinstance(slots, list) or not slots
                or any(not isinstance(slot, dict) or type(slot.get('is_processing')) is not bool
                       for slot in slots)):
            return {'status': 'unknown', 'is_idle': None, 'scope': scope,
                    'reason': 'invalid_slot_response'}
        busy = sum(slot['is_processing'] for slot in slots)
        idle = busy == 0
        return {'status': 'idle' if idle else 'busy', 'is_idle': idle,
                'slot_count': len(slots), 'busy_slots': busy, 'scope': scope}
    except HTTPError as exc:
        exc.close()
        return {'status': 'unknown', 'is_idle': None, 'reason': 'HTTPError', 'scope': scope}
    except Exception as exc:
        # Maintenance status must be useful when inference is down, without leaking
        # credentials, URLs, local paths or response bodies into the conversation.
        return {'status': 'unknown', 'is_idle': None, 'reason': type(exc).__name__, 'scope': scope}


def management_json(home, base, path, *, body=None, timeout=2):
    """Read one bounded local management response without forwarding credentials on redirects."""
    token_path = home/'.opencodex/admin-api-token'
    try:
        if token_path.is_symlink() or not token_path.is_file() or token_path.stat().st_size > 512:
            return None, 'admin_token_file_unavailable'
        token = token_path.read_text(encoding='utf-8').strip()
    except OSError:
        return None, 'admin_token_file_unavailable'
    import re
    if not re.fullmatch(r'ocx_admin_[A-Za-z0-9_-]{43}', token):
        return None, 'admin_token_invalid'
    headers = {'Authorization': 'Bearer '+token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(body).encode('utf-8')
    request = Request(base+path, data=body, headers=headers,
                      method='POST' if body is not None else 'GET')
    # Management credentials must never follow an HTTP redirect to another listener.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(256*1024+1)
        if len(raw) > 256*1024:
            return None, 'management_response_too_large'
        return json.loads(raw), None
    except HTTPError as error:
        error.close()
        return None, f'management_http_{error.code}'
    except (OSError, ValueError):
        return None, 'management_api_unavailable'


def opencodex_request_pacing_activity(home=None, *, provider='strata'):
    """Report only OpenCodex requests tracked by the provider pacing layer."""
    scope = ('OpenCodex 요청 페이싱 계층에서 추적하는 대기·동시성만 표시합니다. 페이싱이 꺼져 있거나 '
             'inFlight가 보고되지 않으면 전체 요청 유휴 상태를 증명하지 않습니다.')
    try:
        home = home or Path.home()
        base, _ = gateway(home)
        data, error = management_json(
            home, base, '/api/provider-request-pacing?'+urlencode({'name': provider}), timeout=2)
        if error:
            return {'status': 'unknown', 'reason': error, 'scope': scope}
        if (not isinstance(data, dict) or data.get('provider') != provider
                or type(data.get('enabled')) is not bool
                or type(data.get('queued')) is not int or data['queued'] < 0
                or type(data.get('nextSlotInMs')) is not int or data['nextSlotInMs'] < 0):
            return {'status': 'unknown', 'reason': 'invalid_pacing_status', 'scope': scope}
        in_flight = data.get('inFlight')
        if in_flight is not None and (type(in_flight) is not int or in_flight < 0):
            return {'status': 'unknown', 'reason': 'invalid_pacing_status', 'scope': scope}
        return {
            'status': 'observed' if data['enabled'] else 'not_tracking',
            'provider': provider,
            'enabled': data['enabled'],
            'queued': data['queued'],
            'next_slot_in_ms': data['nextSlotInMs'],
            'in_flight': in_flight,
            'in_flight_reported': in_flight is not None,
            'scope': scope,
        }
    except (OSError, ValueError, TypeError):
        return {'status': 'unknown', 'reason': 'pacing_status_unavailable', 'scope': scope}


def messages_route_preview(home, base, model):
    """Ask the local management API for a sanitized, read-only Messages route preview."""
    plan, error = management_json(home, base, '/api/protocols/plan', body={
        'model': model, 'inbound': 'messages', 'features': [
            'request.tools', 'request.reasoning', 'request.thinking_budget', 'request.cache_control'
        ]
    })
    if error:
        return {'status': 'unavailable', 'reason': error}

    expected_model = model.removeprefix('strata/')
    candidates = plan.get('candidates', []) if isinstance(plan, dict) else []
    candidate = next((row for row in candidates if isinstance(row, dict)
                      and row.get('provider') == 'strata'
                      and row.get('model') == expected_model), None)
    if candidate is None:
        return {'status': 'unavailable', 'reason': 'strata_candidate_missing'}
    return {
        'status': 'preview',
        'basis': plan.get('basis'),
        'route_kind': plan.get('routeKind'),
        'mode': candidate.get('mode'),
        'request_path': candidate.get('requestPath'),
        'response_path': candidate.get('responsePath'),
        'fidelity': candidate.get('fidelity'),
        'eligible': candidate.get('eligible'),
        'reason_codes': candidate.get('reasonCodes'),
        'feature_effects': candidate.get('featureEffects'),
    }


def messages_tool_search_compatible(preview):
    """Require a direct native Messages route that preserves tool declarations."""
    if (not isinstance(preview, dict) or preview.get('status') != 'preview'
            or preview.get('eligible') is not True or preview.get('mode') != 'native'):
        return False
    effects = preview.get('feature_effects')
    return isinstance(effects, list) and any(
        isinstance(item, dict) and item.get('feature') == 'request.tools'
        and item.get('disposition') == 'passthrough' for item in effects)


def observed_messages_route(home, base, model):
    """Return recent observed Claude Messages routing/latency facts, never request content."""
    expected_model = model.removeprefix('strata/')
    query = urlencode({'provider': 'strata', 'model': expected_model, 'limit': 12})
    data, error = management_json(home, base, '/api/logs?'+query, timeout=1.5)
    if error:
        return {'status': 'unavailable', 'reason': error}
    rows = data.get('logs', []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return {'status': 'unavailable', 'reason': 'invalid_log_response'}
    matches = [row for row in rows if isinstance(row, dict)
               and row.get('provider') == 'strata' and row.get('model') == expected_model
               and row.get('surface') in ('claude', 'claude-desktop')
               and row.get('inboundProtocol') == 'messages']
    if not matches:
        return {'status': 'unavailable', 'reason': 'no_recent_claude_messages'}

    def route_facts(trace):
        if not isinstance(trace, dict):
            return None
        result = {}
        for source, target in [('inbound','inbound'), ('mode','mode'), ('requestPath','request_path'),
                               ('responsePath','response_path'), ('reasonCodes','reason_codes')]:
            value = trace.get(source)
            if isinstance(value, str):
                result[target] = value[:80]
            elif isinstance(value, list) and all(isinstance(item, str) for item in value[:16]):
                result[target] = [item[:80] for item in value[:16]]
        effects = trace.get('featureEffects')
        if isinstance(effects, list):
            result['feature_effects'] = [
                {'feature': item['feature'][:80], 'disposition': item['disposition'][:40]}
                for item in effects[:24] if isinstance(item, dict)
                and isinstance(item.get('feature'), str) and isinstance(item.get('disposition'), str)
            ]
        return result

    successful = [row for row in matches if type(row.get('status')) is int and 200 <= row['status'] < 300]
    durations = [row['durationMs'] for row in successful
                 if type(row.get('durationMs')) in (int, float) and 0 <= row['durationMs'] <= 3_600_000]
    first_response_chunk = [row['firstOutputMs'] for row in successful
                            if type(row.get('firstOutputMs')) in (int, float)
                            and 0 <= row['firstOutputMs'] <= 3_600_000]
    def request_output_rate(row):
        status = row.get('status')
        duration = row.get('durationMs')
        usage = row.get('usage')
        output = usage.get('outputTokens') if isinstance(usage, dict) else None
        if (type(status) is not int or not 200 <= status < 300
                or type(duration) not in (int, float)
                or type(output) is not int or output <= 0
                or duration <= 0 or duration > 3_600_000):
            return None
        return round(output * 1000 / duration, 1)

    def decode_rate(row):
        status = row.get('status')
        if type(status) is not int or not 200 <= status < 300:
            return {'status': 'unavailable', 'reason': 'request_not_successful'}
        metrics = row.get('displayMetrics')
        metric = metrics.get('decodeTokPerSecond') if isinstance(metrics, dict) else None
        if not isinstance(metric, dict):
            return {'status': 'unavailable', 'reason': 'decode_metric_missing'}
        if metric.get('kind') == 'unavailable':
            reason = metric.get('reason')
            allowed_reasons = {'usage_missing', 'usage_unsupported', 'output_missing', 'invalid_duration',
                               'decode_window_too_short', 'ttft_missing', 'combo_attempt_unavailable',
                               'request_not_successful', 'legacy_baseline_not_safe'}
            return {'status': 'unavailable', 'reason': reason if isinstance(reason, str)
                    and reason in allowed_reasons else 'decode_metric_unavailable'}
        value = metric.get('value')
        basis = metric.get('timingBasis')
        if basis == 'legacy-post-visible-output':
            return {'status': 'unavailable', 'reason': 'legacy_baseline_not_safe'}
        if (metric.get('kind') != 'value' or type(value) not in (int, float)
                or not 0 <= value <= 100_000
                or basis != 'generation-window'
                or type(metric.get('estimated')) is not bool):
            return {'status': 'unavailable', 'reason': 'invalid_decode_metric'}
        return {'status': 'observed', 'tokens_per_second': round(value, 1),
                'estimated': metric['estimated'], 'timing_basis': basis}

    def generation_window(row):
        start, end, duration = row.get('genStartMs'), row.get('lastOutputMs'), row.get('durationMs')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or type(duration) not in (int, float) or not 0 <= start <= end <= duration <= 3_600_000):
            return None
        return round(end-start, 1)

    request_rates = [rate for row in successful if (rate := request_output_rate(row)) is not None]
    def decode_rate_groups(rows):
        grouped = {'generation-window': []}
        for row in rows:
            metric = decode_rate(row)
            if metric['status'] == 'observed':
                grouped[metric['timing_basis']].append(metric['tokens_per_second'])
        return {basis: {'median_tokens_per_second': round(median(values), 1),
                        'sample_count': len(values)}
                for basis, values in grouped.items() if values}

    decode_groups = decode_rate_groups(successful)
    by_surface = {}
    for surface in ('claude', 'claude-desktop'):
        surface_rows = [row for row in matches if row.get('surface') == surface]
        surface_successful = [row for row in surface_rows
                              if type(row.get('status')) is int and 200 <= row['status'] < 300]
        surface_durations = [row['durationMs'] for row in surface_successful
                             if type(row.get('durationMs')) in (int, float)
                             and 0 <= row['durationMs'] <= 3_600_000]
        surface_first_chunk = [row['firstOutputMs'] for row in surface_successful
                               if type(row.get('firstOutputMs')) in (int, float)
                               and 0 <= row['firstOutputMs'] <= 3_600_000]
        surface_request_rates = [rate for row in surface_successful
                                 if (rate := request_output_rate(row)) is not None]
        surface_decode_groups = decode_rate_groups(surface_successful)
        by_surface[surface] = {
            'sample_count': len(surface_rows),
            'successful_count': len(surface_successful),
            'median_duration_ms_successful': round(median(surface_durations), 1) if surface_durations else None,
            'median_first_response_chunk_ms_successful': round(median(surface_first_chunk), 1) if surface_first_chunk else None,
            'decode_rate_by_basis': surface_decode_groups,
            'median_request_output_tokens_per_second_successful':
                round(median(surface_request_rates), 1) if surface_request_rates else None,
        }
    latest = matches[-1]
    latest_trace = route_facts(latest.get('protocolTrace'))
    latest_info = {}
    if latest.get('surface') in ('claude', 'claude-desktop'):
        latest_info['surface'] = latest['surface']
    for source, target, maximum in (('timestamp', 'timestamp', 4_102_444_800_000),
                                    ('status', 'status', 599), ('durationMs', 'duration_ms', 3_600_000),
                                    ('firstOutputMs', 'first_response_chunk_ms', 3_600_000)):
        value = latest.get(source)
        if type(value) in (int, float) and 0 <= value <= maximum:
            latest_info[target] = value
    if latest_trace is not None:
        latest_info['route'] = latest_trace
    usage = latest.get('usage')
    if isinstance(usage, dict):
        for source, target in [('inputTokens','input_tokens'), ('cachedInputTokens','cached_input_tokens'),
                               ('outputTokens','output_tokens')]:
            if type(usage.get(source)) is int and usage[source] >= 0:
                latest_info[target] = usage[source]
    latest_info['decode_tokens_per_second'] = decode_rate(latest)
    window_ms = generation_window(latest)
    if window_ms is not None:
        latest_info['generation_window_ms'] = window_ms
    request_rate = request_output_rate(latest)
    if request_rate is not None:
        latest_info['request_output_tokens_per_second'] = request_rate
    failures = [row for row in matches if type(row.get('status')) is int
                and not 200 <= row['status'] < 300]
    failure_summary = {'sample_count': len(failures), 'categories': {}, 'latest': None}
    for row in failures:
        # Return a fixed category, never the raw error: it can contain headers,
        # credentials or request content. A log hint does not authorize a retry.
        error = row.get('upstreamError')
        category = ('upstream_connection_refused' if isinstance(error, str)
                    and re.search(r'\bECONNREFUSED\b', error[:1024], re.IGNORECASE)
                    else 'unclassified_http_error')
        failure_summary['categories'][category] = failure_summary['categories'].get(category, 0) + 1
        recent_failure = {'category': category}
        for source, target, maximum in (('timestamp', 'timestamp', 4_102_444_800_000),
                                        ('status', 'status', 599), ('durationMs', 'duration_ms', 3_600_000)):
            value = row.get(source)
            if type(value) in (int, float) and 0 <= value <= maximum:
                recent_failure[target] = value
        failure_summary['latest'] = recent_failure
    return {
        'status': 'observed',
        'window': 'up to 12 latest Strata model requests, filtered to Claude Messages',
        'sample_count': len(matches),
        'successful_count': len(successful),
        'by_surface': by_surface,
        'non_success_statuses': [row['status'] for row in matches
                                 if type(row.get('status')) is int and not 200 <= row['status'] < 300],
        'failure_summary': failure_summary,
        'median_duration_ms_successful': round(median(durations), 1) if durations else None,
        'median_first_response_chunk_ms_successful': round(median(first_response_chunk), 1) if first_response_chunk else None,
        'decode_rate_by_basis': decode_groups,
        'median_request_output_tokens_per_second_successful':
            round(median(request_rates), 1) if request_rates else None,
        'latest': latest_info,
        'first_response_chunk_scope': 'For Claude Messages this is the first upstream body chunk, not time to first generated or final-answer token.',
        'decode_rate_scope': 'Uses only OpenCodex displayMetrics.decodeTokPerSecond with a generation-window basis. Short windows and legacy first-visible-output estimates remain unavailable.',
        'request_rate_scope': 'Usage output tokens divided by the full end-to-end request duration; includes prefill, reasoning, gateway and stream overhead, so it is not decode speed.',
        'scope': 'Observed OpenCodex request metadata only; no prompt, response, headers, request IDs or credentials are returned. Small recent sample, not a benchmark.',
    }


def context_usage_observation(observed, auto_compact_window):
    """Compare one observed request with the configured Code compaction threshold, not model capacity."""
    if (not isinstance(observed, dict) or observed.get('status') != 'observed'
            or type(auto_compact_window) is not int or auto_compact_window <= 0):
        return {'status': 'unavailable', 'reason': 'request_usage_or_compaction_window_unavailable'}
    latest = observed.get('latest')
    if not isinstance(latest, dict) or type(latest.get('input_tokens')) is not int or latest['input_tokens'] < 0:
        return {'status': 'unavailable', 'reason': 'latest_request_usage_unavailable'}
    input_tokens = latest['input_tokens']
    cached_tokens = latest.get('cached_input_tokens')
    cached_percent = (round(cached_tokens / input_tokens * 100, 1)
                      if type(cached_tokens) is int and 0 <= cached_tokens <= input_tokens and input_tokens else None)
    return {
        'status': 'observed',
        'latest_request_input_tokens': input_tokens,
        'auto_compact_window_tokens': auto_compact_window,
        'window_utilization_percent': round(input_tokens / auto_compact_window * 100, 1),
        'remaining_tokens_to_auto_compact_window': auto_compact_window - input_tokens,
        'cached_input_percent': cached_percent,
        'scope': 'One recent request compared with the saved window, before native compaction/output buffers. This is not the Claude Desktop context meter or exact compaction trigger.',
    }


def saved_compaction_window(settings, model, context):
    """Resolve saved env/model/global precedence without claiming active SDK state."""
    env = settings.get('env', {})
    models = settings.get('modelSettings', {})
    per_model = models.get(model, {}) if isinstance(models, dict) else {}
    candidates = [
        ('environment', env.get('CLAUDE_CODE_AUTO_COMPACT_WINDOW')),
        ('model_settings', per_model.get('autoCompactWindow') if isinstance(per_model, dict) else None),
        ('settings', settings.get('autoCompactWindow')),
    ]
    for source, value in candidates:
        if value == 'auto':
            if source != 'environment':
                return None, source
            continue
        if isinstance(value, str):
            match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([kKmM]?)', value)
            if not match:
                continue
            scale = {'': 1, 'k': 1000, 'm': 1000000}[match[2].lower()]
            value = float(match[1]) * scale
            if not value.is_integer():
                continue
            value = int(value)
        if type(value) is int and 100000 <= value <= 1000000:
            return min(value, context), source
    return None, 'auto'


def publish_files(files, profile, before):
    """Stage first, detect concurrent edits and undo only bytes this setup still owns."""
    changed = {p: body.encode('utf-8') for p, body in files.items() if before[p] != body.encode('utf-8')}
    if not changed:
        return None, 0
    backup = profile/'backups'/('strata-opencodex-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True)
    receipt = {'state': 'preparing', 'files': [], 'published': [], 'rollback_conflicts': []}
    staged = {}
    def current(path):
        return path.read_bytes() if path.exists() else None
    def stage(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.strata-setup-', delete=False) as stream:
            stream.write(data)
            return Path(stream.name)
    def journal():
        direct.write_changed(backup/'files.json', json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    try:
        for index, (path, data) in enumerate(changed.items()):
            name = f'{index}-{path.name}' if before[path] is not None else None
            if name:
                (backup/name).write_bytes(before[path])
            receipt['files'].append({'path': str(path), 'backup': name})
            staged[path] = stage(path, data)
        journal()
        if any(current(path) != original for path, original in before.items()):
            raise ValueError('설정이 다른 작업에서 변경됐습니다. 최신 상태를 확인한 뒤 다시 적용하세요.')
        receipt['state'] = 'applying'
        journal()
        for path, data in changed.items():
            if current(path) != before[path]:
                raise ValueError(f'동시 변경을 감지했습니다: {path}')
            os.replace(staged[path], path)
            receipt['published'].append(str(path))
            journal()
        receipt['state'] = 'committed'
        journal()
    except Exception:
        for raw in reversed(receipt['published']):
            path = Path(raw)
            if current(path) != changed[path]:
                receipt['rollback_conflicts'].append(raw)
                continue
            if before[path] is None:
                path.unlink()
            else:
                restored = stage(path, before[path])
                try:
                    os.replace(restored, path)
                finally:
                    restored.unlink(missing_ok=True)
        receipt['state'] = 'rollback_conflict' if receipt['rollback_conflicts'] else 'rolled_back'
        journal()
        raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
    return backup, len(changed)


def resolve_runtime_python(previous):
    """Keep the working managed interpreter unless the caller explicitly selects one."""
    override = os.environ.get('STRATA_CLAUDE_PYTHON', '').strip()
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            located = shutil.which(override)
            if located:
                candidate = Path(located)
        if not candidate.is_file():
            raise ValueError('STRATA_CLAUDE_PYTHON은 존재하는 Python 실행 파일이어야 합니다.')
        return str(candidate.resolve())

    configured_paths = []
    configured = previous.get('runtime_python') if isinstance(previous, dict) else None
    if isinstance(configured, str) and configured.strip():
        configured_paths.append(configured)
    hook_command = previous.get('hook_command') if isinstance(previous, dict) else None
    match = re.match(r'^\s*"([^"]+)"\s+-X\s+utf8\s+"[^"]+"\s+hook\s*$',
                     hook_command) if isinstance(hook_command, str) else None
    if match:
        configured_paths.append(match.group(1))
    for configured in configured_paths:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    return str(Path(sys.executable).resolve())


def _localize_rea_launcher(source, runtime_python=None):
    """Point imported REA entries at this client checkout."""
    normalized = mcp_config_module.normalize(source)
    rea = normalized['mcpServers'].get('rea')
    args = rea.get('args', []) if isinstance(rea, dict) else []
    launcher = ROOT/'tools/claude_mcp/rea_launcher.py'
    if args and Path(args[0].replace('\\', '/')).name.lower() == 'rea_launcher.py' and launcher.is_file():
        args[0] = str(launcher.resolve())
        if runtime_python:
            rea['command'] = runtime_python
    return normalized


def local_cua_executable(configured=None):
    """Resolve a client-local install, never reuse a missing foreign-machine path."""
    override = os.environ.get('STRATA_CUA_DRIVER_EXE')
    if override:
        selected = Path(override).expanduser()
        if not selected.is_file() or not os.access(selected, os.X_OK):
            raise ValueError('STRATA_CUA_DRIVER_EXE 실행 파일을 확인하세요. 다른 경로로 대체하지 않습니다.')
        return str(selected.resolve())
    if configured:
        selected = Path(configured).expanduser()
        if selected.is_file() and os.access(selected, os.X_OK):
            return str(selected.resolve())
    located = shutil.which('cua-driver')
    if located:
        return str(Path(located).resolve())
    name = 'cua-driver.exe' if sys.platform == 'win32' else 'cua-driver'
    candidates = [Path.home()/'.local/bin'/name]
    if sys.platform == 'darwin':
        candidates.extend([Path('/Applications/CuaDriver.app/Contents/MacOS/cua-driver'),
                           Path.home()/'Applications/CuaDriver.app/Contents/MacOS/cua-driver'])
    for selected in candidates:
        if selected.is_file() and os.access(selected, os.X_OK):
            return str(selected.resolve())
    raise ValueError('이 PC의 CUA Driver가 없습니다. https://cua.ai/docs/cua-driver/quickstart 에서 설치한 뒤 다시 실행하세요. 다른 경로이면 STRATA_CUA_DRIVER_EXE를 지정하세요.')


def default_client_mcp_source():
    """A fresh PC uses the same guarded CUA and pinned REA launchers as this repo."""
    node = shutil.which('node')
    if not node or not shutil.which('npx'):
        raise ValueError('새 PC에는 Node.js와 npm이 필요합니다. https://nodejs.org/en/download 에서 설치하고 새 터미널에서 다시 실행하세요.')
    return {'mcpServers': {
        'cua-driver': {'type': 'stdio', 'command': node,
            'args': [str(ROOT/'tools/cua-driver/mcp.mjs')],
            'env': {'CUA_DRIVER_EXE': local_cua_executable(),
                    'CUA_DRIVER_POLICY_FILE': str(ROOT/'tools/cua-driver/window-scoped.rego'),
                    'CUA_DRIVER_PERMISSION_MODE': 'standard', 'STRATA_CUA_CATALOG_REVISION': '2'}},
        'rea': {'type': 'stdio', 'command': str(Path(sys.executable).resolve()),
            'args': [str(ROOT/'tools/claude_mcp/rea_launcher.py'), 'rea-agents@6.7.0', 'mcp']}}}


def desktop_config_library(home):
    """Match OpenCodex/Desktop platform paths without assuming Windows AppData."""
    configured = os.environ.get('CLAUDE_3P_CONFIG_LIBRARY') or os.environ.get('OPENCODEX_CLAUDE_DESKTOP_CONFIG_DIR')
    if configured:
        return Path(configured).expanduser()
    explicit = os.environ.get('CLAUDE_USER_DATA_DIR')
    if explicit:
        return Path(explicit).expanduser()/'configLibrary'
    actual_home = home.expanduser().resolve() == Path.home().resolve()
    if sys.platform == 'darwin':
        root = home/'Library/Application Support/Claude-3p'
    elif sys.platform.startswith('linux'):
        xdg = os.environ.get('XDG_CONFIG_HOME') if actual_home else None
        root = (Path(xdg) if xdg else home/'.config')/'Claude-3p'
    else:
        local = os.environ.get('LOCALAPPDATA') if actual_home else None
        root = (Path(local) if local else home/'AppData/Local')/'Claude-3p'
    return root/'configLibrary'


def _localize_cua_launcher(source):
    """Point imported CUA entries at the application-neutral repository wrapper."""
    normalized = mcp_config_module.normalize(source)
    cua = normalized['mcpServers'].get('cua-driver')
    if not isinstance(cua, dict):
        return normalized
    args = cua.get('args', [])
    wrapper = ROOT/'tools/cua-driver/mcp.mjs'
    if args and Path(args[0].replace('\\', '/')).name.lower() == 'mcp.mjs' and wrapper.is_file():
        args[0] = str(wrapper.resolve())
    environment = cua.get('env')
    if isinstance(environment, dict):
        policy = ROOT/'tools/cua-driver/window-scoped.rego'
        configured_driver = environment.get('CUA_DRIVER_EXE')
        if configured_driver:
            environment['CUA_DRIVER_EXE'] = local_cua_executable(configured_driver)
        configured_policy = environment.get('CUA_DRIVER_POLICY_FILE')
        if (isinstance(configured_policy, str)
                and Path(configured_policy.replace('\\', '/')).name.lower() == 'window-scoped.rego'
                and policy.is_file()):
            environment['CUA_DRIVER_POLICY_FILE'] = str(policy.resolve())
    command = cua.get('command')
    if isinstance(command, str) and Path(command.replace('\\', '/')).name.lower() in ('node', 'node.exe'):
        located = shutil.which('node')
        if located:
            cua['command'] = str(Path(located).resolve())
        elif not Path(command).is_file():
            raise ValueError('CUA Driver 연결에는 Node.js가 필요합니다. Node.js 설치 뒤 Claude 설정을 다시 적용하세요.')
    return normalized


def resolve_mcp_source(home, mcp_config=None):
    """Load the Claude-owned MCP source, optionally importing a Claude-format file."""
    runtime_python = resolve_runtime_python(read_json(home/'.claude'/STATE, {}))
    source_path = home/'.claude'/MCP_SOURCE
    if source_path.is_file():
        original = mcp_config_module.read(source_path)
        source = _localize_cua_launcher(_localize_rea_launcher(original, runtime_python))
        payload = (json.dumps(source, ensure_ascii=False, indent=2)+'\n'
                   if source != original else None)
        return source, payload, source_path

    if mcp_config is not None:
        source = mcp_config_module.read(mcp_config)
    else:
        native = read_json(home/'.claude.json', {}).get('mcpServers', {})
        native_source = {'mcpServers': {name: native[name] for name in
            ('cua-driver', 'rea', 'strata-maintenance') if name in native}}
        try:
            source = mcp_config_module.normalize(native_source)
        except ValueError:
            if native_source['mcpServers']:
                raise
            source = default_client_mcp_source()

    source = _localize_cua_launcher(_localize_rea_launcher(source, runtime_python))
    payload = json.dumps(source, ensure_ascii=False, indent=2)+'\n'
    return source, payload, source_path


def claude_mcp_projection(source, mcp_source_path, *, lazy_cua_rea=True, runtime_python=None):
    """Project Claude-owned servers; optionally replace CUA/REA with a small dispatcher."""
    projected = mcp_config_module.normalize(source)['mcpServers']
    if 'strata-maintenance' in projected and runtime_python:
        projected['strata-maintenance']['command'] = runtime_python
    rea = projected.get('rea')
    if (runtime_python and isinstance(rea, dict) and rea.get('args')
            and Path(rea['args'][0]).resolve() ==
                (ROOT/'tools/claude_mcp/rea_launcher.py').resolve()):
        rea['command'] = runtime_python
    if not lazy_cua_rea:
        return projected
    if not any(name in projected for name in ('cua-driver', 'rea')):
        raise ValueError('지연 CUA/REA 연결에 사용할 활성 로컬 MCP가 없습니다.')
    dispatcher = ROOT/'tools/claude_mcp/lazy_dispatcher.py'
    if not dispatcher.is_file():
        raise ValueError('지연 CUA/REA MCP 디스패처 파일이 없습니다.')
    for name in ('cua-driver', 'rea'):
        projected.pop(name, None)
    projected['agent-tools'] = {
        'type': 'stdio',
        'command': runtime_python or str(Path(sys.executable).resolve()),
        'args': [str(dispatcher.resolve()), '--mcp-config', str(Path(mcp_source_path).resolve())],
    }
    return projected


READ_ONLY_MAINTENANCE_TOOLS = (
    'environment_status', 'opencodex_service_status', 'restart_status', 'desktop_restart_status')
MANAGED_PERMISSION_RULES = {
    'mcp__agent-tools__search_tools',
    *(f'mcp__strata-maintenance__{name}' for name in READ_ONLY_MAINTENANCE_TOOLS),
}


def mcp_permission_matches(allow_rules, tool_name):
    """Match server-anchored MCP allow globs without treating bare '*' as approval."""
    parts = tool_name.split('__', 2) if isinstance(tool_name, str) else []
    if len(parts) != 3 or parts[0] != 'mcp' or not all(parts):
        return False
    prefix = f'mcp__{parts[1]}__'
    return any(isinstance(rule, str) and rule.startswith(prefix) and fnmatchcase(tool_name, rule)
               for rule in allow_rules)


def mcp_tool_rule_matches(rules, tool_name):
    """Match an exact or globbed MCP tool name in ask/deny settings."""
    return any(isinstance(rule, str) and fnmatchcase(tool_name, rule) for rule in rules)


def mcp_server_digest(server):
    return hashlib.sha256(json.dumps(server, sort_keys=True).encode('utf-8')).hexdigest()


def maintenance_project_path():
    """Match Claude's shared primary-project scope for a linked Git worktree."""
    root = ROOT.resolve()
    if (root/'.git').is_file():
        try:
            result = subprocess.run(['git', '-c', 'core.quotepath=false', 'rev-parse',
                '--path-format=absolute', '--git-common-dir'], cwd=root,
                capture_output=True, text=True, encoding='utf-8', timeout=3)
            common = Path(result.stdout.strip())
            if result.returncode == 0 and common.name == '.git' and common.is_dir():
                root = common.resolve().parent
        except (OSError, subprocess.TimeoutExpired):
            pass
    return root.as_posix()


def scope_maintenance_mcp(native, server, previous):
    """Keep maintenance local to this checkout, preserving project state and toggles."""
    name = 'strata-maintenance'
    prior = previous.get('maintenance_mcp') or {}
    if server is None and not prior:
        return None
    projects = native.setdefault('projects', {})
    if not isinstance(projects, dict):
        raise ValueError('Claude projects 설정이 객체가 아니어서 유지보수 MCP를 옮길 수 없습니다.')
    project_path = maintenance_project_path()
    # Reuse the existing project key on Windows even if its path spelling differs.
    project_path = next((key for key in projects
        if os.path.normcase(os.path.normpath(key)) ==
           os.path.normcase(os.path.normpath(project_path))), project_path)
    prior_project = prior.get('project')
    if prior_project and (prior_project != project_path or server is None):
        old = projects.get(prior_project, {}).get('mcpServers', {})
        if name in old:
            if mcp_server_digest(old[name]) != prior.get('server_sha256'):
                raise ValueError('기존 프로젝트의 유지보수 MCP가 변경되어 보존합니다. 연결을 먼저 확인하세요.')
            old.pop(name)
    if server is None:
        return None
    project = projects.setdefault(project_path, {})
    if not isinstance(project, dict):
        raise ValueError('Claude 유지보수 프로젝트 설정이 객체가 아닙니다.')
    local = project.setdefault('mcpServers', {})
    if not isinstance(local, dict):
        raise ValueError('Claude 프로젝트 mcpServers 설정이 객체가 아닙니다.')
    owned_local = (prior_project == project_path and name in local
        and mcp_server_digest(local[name]) == prior.get('server_sha256'))
    if name in local and local[name] != server and not owned_local:
        raise ValueError('기존 프로젝트 유지보수 MCP 설정은 보존합니다. 연결을 먼저 확인하세요.')
    global_servers = native.setdefault('mcpServers', {})
    if name in global_servers:
        if (name not in previous.get('managed_mcp_servers', [])
                and global_servers[name] != server):
            raise ValueError('기존 사용자 유지보수 MCP 설정은 보존합니다. 연결을 먼저 확인하세요.')
        global_servers.pop(name)
    local[name] = server
    return {'project': project_path, 'server_sha256': mcp_server_digest(server)}


def setup(home, *, verify=True, lazy_cua_rea=True, mcp_config=None):
    """Merge only owned fields; retain other settings, MCP servers and user state."""
    base, model = gateway(home)
    context = health(base, model, home=home) if verify else 262144
    profile = home/'.claude'
    assets = direct.managed_guidance(profile, lazy_cua_rea=lazy_cua_rea)
    maintenance_guide = ROOT/'docs/CLAUDE_SELF_MAINTENANCE_KO.md'
    if maintenance_guide.is_file():
        assets['guidance/maintenance.md'] = maintenance_guide.read_text(encoding='utf-8')
        assets['CLAUDE.md'] += ('\n## 이 실행 환경 유지보수\n\n'
            'Strata·OpenCodex·Claude Desktop Code 자체를 점검하거나 변경할 때만 '
            f'`{(profile/"guidance/maintenance.md").as_posix()}`를 먼저 읽는다. '
            '일반 프로젝트 작업에는 이 상세 절차를 읽지 않는다. '
            f'유지보수 작업은 `{ROOT.resolve().as_posix()}`에서 진행하며, '
            '유지보수 MCP는 해당 Git 저장소의 프로젝트 범위에만 등록한다.\n')
    previous = read_json(profile/STATE, {})
    runtime_python = resolve_runtime_python(previous)
    source, mcp_source_payload, mcp_source_path = resolve_mcp_source(home, mcp_config)
    tracked = [profile/STATE, profile/'settings.json', profile/MCP_SOURCE, home/'.claude.json',
               *[profile/name for name in assets]]
    before = {p: p.read_bytes() if p.exists() else None for p in tracked}
    settings = read_json(profile/'settings.json', {})
    native = read_json(home/'.claude.json', {})
    projected = claude_mcp_projection(source, mcp_source_path, lazy_cua_rea=lazy_cua_rea,
                                      runtime_python=runtime_python)
    settings_env = settings.get('env')
    configured_search_url = settings_env.get('SEARXNG_URL') if isinstance(settings_env, dict) else None
    if 'agent-tools' in projected:
        projected_agent_env = projected['agent-tools'].setdefault('env', {})
        prior_servers = native.get('mcpServers', {})
        prior_agent = prior_servers.get('agent-tools', {}) if isinstance(prior_servers, dict) else {}
        prior_agent_env = prior_agent.get('env', {}) if isinstance(prior_agent, dict) else {}
        if not isinstance(projected_agent_env, dict) or not isinstance(prior_agent_env, dict):
            raise ValueError('agent-tools 환경 설정이 객체가 아니어서 검색 키를 안전하게 보존할 수 없습니다.')
        # These provider credentials are kept only in the user's MCP entry. Preserve them
        # when setup regenerates that entry from the imported CUA/REA source config.
        for name in ('EXA_API_KEY', 'TAVILY_API_KEY'):
            value = prior_agent_env.get(name)
            if isinstance(value, str) and value:
                projected_agent_env[name] = value
        if configured_search_url:
            projected_agent_env['SEARXNG_URL'] = searxng_search.normalize_base_url(configured_search_url)
        elif not projected_agent_env:
            projected['agent-tools'].pop('env', None)
    maintenance_server = projected.pop('strata-maintenance', None)
    maintenance_mcp = scope_maintenance_mcp(native, maintenance_server, previous)
    direct.validate_managed_guidance(profile, assets, previous)
    if settings.get('env', {}).get('CLAUDE_CONFIG_DIR'):
        raise ValueError('공통 설정 안의 CLAUDE_CONFIG_DIR 재지정을 먼저 확인하세요.')

    env = settings.setdefault('env', {})
    env.update(ANTHROPIC_BASE_URL=base, ANTHROPIC_AUTH_TOKEN='opencodex-proxy',
        ANTHROPIC_MODEL=model, ANTHROPIC_SMALL_FAST_MODEL=model,
        ANTHROPIC_DEFAULT_OPUS_MODEL=model, ANTHROPIC_DEFAULT_SONNET_MODEL=model,
        ANTHROPIC_DEFAULT_HAIKU_MODEL=model, CLAUDE_CODE_SUBAGENT_MODEL=model,
        ANTHROPIC_CUSTOM_MODEL_OPTION=model, ANTHROPIC_CUSTOM_MODEL_OPTION_NAME='Strata (OpenCodex)',
        ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION='OpenCodex를 경유하는 로컬 Strata 모델',
        ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES='effort,thinking',
        CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(context),
        CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(direct.context_limits(context)[0]),
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', CLAUDE_CODE_MAX_RETRIES='2',
        # Keep Claude Code's model-aware default: a custom Strata model did not expose
        # ToolSearch in the live Desktop Code check, even when forced with `true`.
        API_TIMEOUT_MS='300000', ENABLE_TOOL_SEARCH='auto', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    window = direct.context_limits(context)[1]
    if window != 'auto':
        env['CLAUDE_CODE_AUTO_COMPACT_WINDOW'] = str(window)
    else:
        env.pop('CLAUDE_CODE_AUTO_COMPACT_WINDOW', None)
    env.setdefault('CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT', '1')
    for family in ('OPUS', 'SONNET', 'HAIKU'):
        env['ANTHROPIC_DEFAULT_'+family+'_MODEL_SUPPORTED_CAPABILITIES'] = 'effort,thinking'
    if os.name == 'nt':
        env['CLAUDE_CODE_USE_POWERSHELL_TOOL'] = '1'
        bash = Path(r'C:\Program Files\Git\bin\bash.exe')
        if bash.is_file():
            env['CLAUDE_CODE_GIT_BASH_PATH'] = str(bash)
    settings.update(model=model, autoCompactWindow=window)
    # Carry prior deliberate preferences over once; future setup preserves the shared choices.
    legacy = read_json(home/'.config/strata/claude-code/settings.json', {})
    for key, fallback in [('effortLevel', 'medium'), ('alwaysThinkingEnabled', True), ('language', 'korean')]:
        settings.setdefault(key, legacy.get(key, fallback))
    permissions = settings.setdefault('permissions', {})
    if not isinstance(permissions, dict):
        raise ValueError('Claude 권한 설정이 객체가 아니어서 MCP 권한을 안전하게 병합할 수 없습니다.')
    permissions.setdefault('defaultMode',
        legacy.get('permissions', {}).get('defaultMode', 'bypassPermissions'))
    # Allow only the lazy dispatcher catalog lookup and exact read-only maintenance
    # queries. Execution, restart, and cancellation actions remain permission-gated.
    search_permission = 'mcp__agent-tools__search_tools'
    maintenance_permissions = ({f'mcp__strata-maintenance__{name}'
        for name in READ_ONLY_MAINTENANCE_TOOLS} if maintenance_server else set())
    requested_managed_permissions = ({search_permission} if lazy_cua_rea else set()) | maintenance_permissions
    allow_rules = permissions.setdefault('allow', [])
    if not isinstance(allow_rules, list):
        raise ValueError('Claude permissions.allow가 목록이 아니어서 MCP 권한을 안전하게 병합할 수 없습니다.')
    prior_managed_permissions = set(previous.get('managed_permission_rules', [])) & MANAGED_PERMISSION_RULES
    desired_managed_permissions = set()
    for tool_name in requested_managed_permissions:
        user_rule_covers_tool = any(
            rule not in prior_managed_permissions and mcp_permission_matches([rule], tool_name)
            for rule in allow_rules)
        if user_rule_covers_tool:
            continue
        if tool_name not in allow_rules:
            allow_rules.append(tool_name)
            desired_managed_permissions.add(tool_name)
        elif tool_name in prior_managed_permissions:
            desired_managed_permissions.add(tool_name)
    for rule in prior_managed_permissions-desired_managed_permissions:
        allow_rules[:] = [entry for entry in allow_rules if entry != rule]
    command = f'"{Path(runtime_python).as_posix()}" -X utf8 "{Path(__file__).resolve().as_posix()}" hook'
    commands = {command, previous.get('hook_command')}
    hooks = settings.setdefault('hooks', {})
    # The language policy is already in generated CLAUDE.md; keep this process off every prompt.
    prompt_hooks = direct.merge_hook(hooks.get('UserPromptSubmit', []), None, commands)
    if prompt_hooks:
        hooks['UserPromptSubmit'] = prompt_hooks
    else:
        hooks.pop('UserPromptSubmit', None)
    hooks['SessionStart'] = direct.merge_hook(hooks.get('SessionStart', []), {
        'matcher': 'startup|resume|clear|compact|fork',
        'hooks': [{'type': 'command', 'command': command, 'timeout': 3}],
    }, commands)

    servers = native.setdefault('mcpServers', {})
    owned = set(previous.get('managed_mcp_servers', []))
    for name, server in projected.items():
        if name in servers and name not in owned and servers[name] != server:
            raise ValueError(f'기존 사용자 MCP 설정은 보존합니다. 연결을 먼저 확인하세요: {name}')
        servers[name] = server
    for name in owned-set(projected):
        servers.pop(name, None)
    state = {'version': 1, 'base_url': base, 'model': model, 'context': context,
        'mcp_source_config': str(mcp_source_path.resolve()), 'runtime_python': runtime_python, 'hook_command': command,
        'managed_mcp_servers': list(projected),
        'managed_permission_rules': sorted(desired_managed_permissions),
        'managed_guidance_sha256': {name: hashlib.sha256(body.encode('utf-8')).hexdigest()
                                   for name, body in assets.items()}}
    if maintenance_mcp:
        state['maintenance_mcp'] = maintenance_mcp
    if lazy_cua_rea:
        state['lazy_cua_rea'] = True
    files = {profile/name: body for name, body in assets.items()}
    if mcp_source_payload is not None:
        files[mcp_source_path] = mcp_source_payload
    for path, document in [(profile/'settings.json', settings), (home/'.claude.json', native), (profile/STATE, state)]:
        files[path] = json.dumps(document, ensure_ascii=False, indent=2)+'\n'
    backup, changed = publish_files(files, profile, before)
    return {'base_url': base, 'model': model, 'context': context, 'profile': str(profile),
            'mcp': list(projected), 'mcp_source_config': str(mcp_source_path.resolve()),
            'maintenance_project': maintenance_mcp['project'] if maintenance_mcp else None,
            'changed': changed, 'backup': str(backup) if backup else None}


def diagnose(home):
    """Return typed readiness and ownership paths; never serialize configuration secrets."""
    base, model = gateway(home)
    settings = read_json(home/'.claude/settings.json')
    # A status tool must not refresh unrelated cloud-provider catalogs. Setup still
    # checks model discovery; maintenance checks the actual local model directly.
    context = health(base, model, home=home, discover=False)
    config = read_json(home/'.opencodex/config.json')
    adapter = config.get('providers', {}).get('strata', {}).get('adapter')
    native = config.get('protocols', {}).get('rollout', {}).get('managedMessagesNative') is True
    transport = {'strata_adapter': adapter, 'managed_messages_native': native,
                 'native_messages_configured': adapter == 'anthropic' and native,
                 'messages_route_preview': messages_route_preview(home, base, model),
                 'messages_route_observed': observed_messages_route(home, base, model),
                 'scope': 'Configuration and a read-only route preview; actual recent Claude Messages traces are reported separately. Search, image processing or policy may select the bridge.'}
    env = settings.get('env', {})
    ownership = read_json(home/'.claude'/STATE, {})
    native = read_json(home/'.claude.json', {})
    native_servers = native.get('mcpServers', {})
    managed_servers = ownership.get('managed_mcp_servers', [])
    mcp_source_path = Path(ownership.get('mcp_source_config') or home/'.claude'/MCP_SOURCE)
    mcp_configured = isinstance(managed_servers, list) and bool(managed_servers) and all(
        isinstance(name, str) and name in native_servers for name in managed_servers) and mcp_source_path.is_file()
    maintenance_owner = ownership.get('maintenance_mcp') or {}
    maintenance_project = maintenance_owner.get('project')
    maintenance_settings = native.get('projects', {}).get(maintenance_project, {})
    local_maintenance = maintenance_settings.get('mcpServers', {}).get('strata-maintenance')
    maintenance_configured = (local_maintenance is not None
        and mcp_server_digest(local_maintenance) == maintenance_owner.get('server_sha256'))
    if maintenance_owner:
        mcp_configured = (mcp_configured and maintenance_configured
            and 'strata-maintenance' not in native_servers)
    else:
        # Older installations kept the optional maintenance server at user scope.
        maintenance_configured = ('strata-maintenance' in managed_servers
            and 'strata-maintenance' in native_servers) if isinstance(managed_servers, list) else False
    # Older ownership receipts already named agent-tools but omitted the mode
    # flag. Still validate the registered dispatcher and its permissions.
    inferred_lazy_cua_rea = (ownership.get('lazy_cua_rea') is not True
        and isinstance(managed_servers, list) and 'agent-tools' in managed_servers)
    lazy_cua_rea = ownership.get('lazy_cua_rea') is True or inferred_lazy_cua_rea
    if lazy_cua_rea:
        entry = native_servers.get('agent-tools', {})
        entry_args = entry.get('args', []) if isinstance(entry, dict) else []
        dispatcher_path = ROOT/'tools/claude_mcp/lazy_dispatcher.py'
        mcp_configured = (mcp_configured and dispatcher_path.is_file()
            and isinstance(entry, dict) and Path(entry.get('command', '')).is_file()
            and str(dispatcher_path.resolve()) in entry_args
            and '--mcp-config' in entry_args
            and str(mcp_source_path.resolve()) in entry_args)
    mcp_delivery = {
        'mode': 'on_demand_cua_rea' if lazy_cua_rea else 'direct',
        'mode_inferred_from_managed_server': inferred_lazy_cua_rea,
        'status': 'configured' if mcp_configured else 'mismatch',
        'managed_servers': managed_servers if isinstance(managed_servers, list) else [],
        'additional_user_servers': sorted(name for name in native_servers
            if name not in (managed_servers if isinstance(managed_servers, list) else [])),
        'duplicate_direct_servers': sorted(set(native_servers) & {'cua-driver', 'rea'}) if lazy_cua_rea else [],
        'maintenance': {
            'scope': 'local' if maintenance_owner else 'user' if maintenance_configured else None,
            'project': maintenance_project,
            'configured': maintenance_configured,
            'enabled_for_project': maintenance_configured and 'strata-maintenance' not in
                maintenance_settings.get('disabledMcpServers', []),
            'registered_for_all_projects': 'strata-maintenance' in native_servers},
        'runtime_status': 'not_verified',
        'scope': 'Saved MCP configuration only; a new Claude Code session must load and exercise the tool.'}
    permissions = settings.get('permissions', {})
    allow_rules = permissions.get('allow', []) if isinstance(permissions, dict) else []
    allow_rules = allow_rules if isinstance(allow_rules, list) else []
    search_permission = 'mcp__agent-tools__search_tools'
    call_permission = 'mcp__agent-tools__call_tool'
    search_rule_matches = mcp_permission_matches(allow_rules, search_permission)
    call_rule_matches = mcp_permission_matches(allow_rules, call_permission)
    maintenance_read_permissions = {
        name: mcp_permission_matches(allow_rules, f'mcp__strata-maintenance__{name}')
        for name in READ_ONLY_MAINTENANCE_TOOLS}
    ask_rules = permissions.get('ask', []) if isinstance(permissions, dict) else []
    deny_rules = permissions.get('deny', []) if isinstance(permissions, dict) else []
    ask_rules = ask_rules if isinstance(ask_rules, list) else []
    deny_rules = deny_rules if isinstance(deny_rules, list) else []
    search_asked = mcp_tool_rule_matches(ask_rules, search_permission)
    search_denied = mcp_tool_rule_matches(deny_rules, search_permission)
    permission_status = ('not_applicable' if not lazy_cua_rea else
                         'blocked_by_deny' if search_denied else
                         'requires_confirmation' if search_asked else
                         'configured' if search_rule_matches else 'missing')
    mcp_permissions_configured = not lazy_cua_rea or permission_status == 'configured'
    mcp_permissions = {
        'status': permission_status,
        'search_tool_allowed_by_rules': search_rule_matches,
        'search_tool_asked_by_rules': search_asked,
        'search_tool_denied_by_rules': search_denied,
        'call_tool_allowed_by_rules': call_rule_matches,
        'maintenance_server_configured': maintenance_configured,
        'maintenance_read_tools_allowed_by_rules': maintenance_read_permissions,
        'runtime_status': 'not_verified',
        'scope': 'Saved MCP permission rules only, evaluated in deny/ask/allow precedence; the current session mode and existing Desktop approval prompts are not evaluated.'}
    default_mode = permissions.get('defaultMode', 'default') if isinstance(permissions, dict) else None
    desktop_modes = {'default', 'acceptEdits', 'plan', 'auto', 'bypassPermissions'}
    desktop_mode_status = ('configured' if isinstance(default_mode, str) and default_mode in desktop_modes else
                           'unsupported_for_desktop' if default_mode == 'dontAsk' else 'invalid')
    desktop_permission_mode = {
        'default_mode': default_mode,
        'status': desktop_mode_status,
        'runtime_status': 'not_verified',
        'scope': 'Saved default for new Desktop Code sessions only; a previously selected folder mode and the current session mode are not observed.'}
    saved_effort = settings.get('effortLevel')
    effort_level = {
        'saved_default': saved_effort if isinstance(saved_effort, str) else None,
        'status': ('configured' if isinstance(saved_effort, str)
                   and saved_effort in {'low', 'medium', 'high'}
                   else 'missing' if saved_effort is None else 'invalid'),
        'runtime_status': 'not_verified',
        'scope': 'Saved Claude Code default only; the current Desktop session and per-request reasoning level are not observed.'}
    configured = env.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS', '')
    configured = int(configured) if isinstance(configured, str) and configured.isascii() and configured.isdecimal() else 0
    model_window = min(configured, context) if configured else context
    compact_window, compact_source = saved_compaction_window(settings, model, model_window)
    context_window_policy = {
        'model_context_tokens': model_window,
        'auto_compact_window_tokens': compact_window,
        'source': compact_source,
        'status': ('automatic' if compact_window is None else
                   'full_model_window' if compact_window == model_window else 'reduced_window'),
        'runtime_status': 'not_verified',
        'scope': 'Saved configuration only. Claude reserves a native buffer inside this window; active Desktop/CLI overrides and the exact compaction trigger are not observed.'}
    tool_search = env.get('ENABLE_TOOL_SEARCH')
    tool_search_route_preview_ready = (tool_search in ('auto', 'true')
        and transport['native_messages_configured']
        and messages_tool_search_compatible(transport['messages_route_preview']))
    checks = {'shared_route': env.get('ANTHROPIC_BASE_URL') == base,
              'shared_model': settings.get('model') == env.get('ANTHROPIC_MODEL') == model,
              'context': 4096 <= configured <= context,
              'managed_mcp_configuration': mcp_configured,
              'managed_mcp_permission_configuration': mcp_permissions_configured,
              'desktop_permission_mode_configuration': desktop_mode_status == 'configured',
              'mcp_tool_search_route_preview': tool_search_route_preview_ready,
              'strata_loaded': True}
    desktop = desktop_config_library(home)
    info = {'available': False, 'ready': False, 'status': 'not_configured'}
    try:
        if (desktop/'_meta.json').is_file():
            import uuid
            selected = str(uuid.UUID(read_json(desktop/'_meta.json').get('appliedId', '')))
            profile = read_json(desktop/(selected+'.json'))
            defaults = [m for m in profile.get('inferenceModels', []) if m.get('isFamilyDefault')]
            mapped = model in config.get('claudeCode', {}).get('desktopProfile', {}).get('defaults', {}).values()
            checks['desktop_gateway'] = profile.get('inferenceProvider') == 'gateway' and profile.get('inferenceGatewayBaseUrl') == base
            checks['desktop_default'] = bool(defaults) and mapped
            desktop_ready = checks['desktop_gateway'] and checks['desktop_default']
            info = {'available': True, 'ready': desktop_ready,
                    'status': 'ready' if desktop_ready else 'profile_mismatch',
                    'base_url': profile.get('inferenceGatewayBaseUrl'),
                    'default_wire_models': [m.get('name') for m in defaults],
                    'tool_search': {
                        'configured': profile.get('toolSearchEnabled'),
                        'enabled_in_profile': profile.get('toolSearchEnabled') is True,
                        'runtime_status': 'not_verified',
                        'note': ('Gateway Desktop sessions require toolSearchEnabled=true in '
                                 'the applied Desktop profile; ENABLE_TOOL_SEARCH alone does not '
                                 'lift Desktop suppression. Confirm deferred tools and tool calls '
                                 'in a new Desktop session after restarting the app.')}}
    except (OSError, ValueError, TypeError, AttributeError):
        info = {'available': True, 'ready': False, 'status': 'invalid_profile'}
    desktop_ready = bool(info['ready'])
    # Saved cross-client differences are setup diagnostics, not Claude readiness
    # gates. A malformed/uninstalled Codex client must not break Claude's doctor.
    try:
        if __package__:
            from .strata_client_settings import audit
        else:
            from strata_client_settings import audit
        client_settings = audit(home)
    except (OSError, ValueError, TypeError, AttributeError):
        client_settings = {'configured': False, 'runtime_status': 'not_verified',
                           'status': 'invalid_saved_client_config'}
    return {'ready': all(checks.values()), 'checks': checks, 'base_url': base, 'model': model,
            'context': min(configured, context) if configured else context, 'server_context': context, 'desktop': info,
            'desktop_ready': desktop_ready,
            'host_memory': host_memory_status(),
            'transport': transport,
            'opencodex_request_pacing': opencodex_request_pacing_activity(home),
            'context_usage': context_usage_observation(
                transport['messages_route_observed'], compact_window),
            'context_window_policy': context_window_policy,
            'mcp_delivery': mcp_delivery,
            'mcp_permissions': mcp_permissions,
            'desktop_permission_mode': desktop_permission_mode,
            'effort_level': effort_level,
            'client_settings': client_settings,
            'mcp_tool_search': {
                'configured': tool_search,
                'mode': ('model_aware_threshold_deferred'
                         if tool_search == 'auto' else 'always_deferred' if tool_search == 'true'
                         else 'all_tools_preloaded' if tool_search == 'false' else 'unconfigured'),
                'route_preview_compatible': tool_search_route_preview_ready,
                'runtime_status': 'not_verified',
                'scope': 'The readiness check covers configuration and a sanitized native Messages route preview only. It does not prove that the current model exposes ToolSearch or that deferred schemas work. Confirm runtime support in a new Claude Code session before claiming tool-search or context savings.'},
            'profile': str(home/'.claude'),
            'mcp': list(read_json(home/'.claude.json', {}).get('mcpServers', {})),
            'maintenance_guide': str(home/'.claude/guidance/maintenance.md')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'doctor', 'run', 'hook'])
    parser.add_argument('--project', type=Path)
    parser.add_argument('--choose-project', action='store_true')
    parser.add_argument('--mcp-config', type=Path,
                        help='Claude 형식 CUA/REA MCP 설정을 Claude 프로필에 한 번 가져옵니다 (setup 전용)')
    mcp_mode = parser.add_mutually_exclusive_group()
    mcp_mode.add_argument('--lazy-cua-rea', dest='lazy_cua_rea', action='store_true',
                        help='setup에서 CUA/REA를 필요할 때 검색·호출 (기본값)')
    mcp_mode.add_argument('--direct-cua-rea', dest='lazy_cua_rea', action='store_false',
                        help='setup에서 CUA/REA 전체 MCP 도구를 직접 등록')
    parser.set_defaults(lazy_cua_rea=None)
    args, extra = parser.parse_known_args(argv)
    if extra[:1] == ['--']:
        extra = extra[1:]
    if args.action != 'run' and extra:
        parser.error('setup/doctor에는 Claude Code 실행 인자를 전달할 수 없습니다.')
    if args.action == 'hook':
        for stream in (sys.stdin, sys.stdout):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        event = json.load(sys.stdin)
        name = event.get('hook_event_name', 'UserPromptSubmit')
        if name == 'SessionStart':
            if __package__:
                from .claude_desktop_runtime import record_session_start
            else:
                from claude_desktop_runtime import record_session_start
            record_session_start(event)
        if name in ('UserPromptSubmit', 'SessionStart'):
            print(json.dumps({'hookSpecificOutput': {'hookEventName': name,
                'additionalContext': direct.hook_context(event)}}, ensure_ascii=False))
        return 0
    if args.action != 'setup' and args.lazy_cua_rea is not None:
        parser.error('--lazy-cua-rea/--direct-cua-rea는 setup에서만 사용할 수 있습니다.')
    if args.action != 'setup' and args.mcp_config:
        parser.error('--mcp-config은 setup에서만 사용할 수 있습니다.')
    home = Path.home()
    if args.action == 'setup':
        mcp_config = args.mcp_config.expanduser().resolve() if args.mcp_config else None
        print(json.dumps(setup(home, mcp_config=mcp_config,
                               lazy_cua_rea=args.lazy_cua_rea is not False), ensure_ascii=False))
        return 0
    settings = read_json(home/'.claude/settings.json')
    base, model = gateway(home)
    if settings.get('env', {}).get('ANTHROPIC_BASE_URL') != base or settings.get('model') != model:
        raise ValueError('공통 연결이 현재 OpenCodex 설정과 다릅니다. setup-claude-opencodex.bat를 실행하세요.')
    if args.action == 'doctor':
        report = diagnose(home)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report['ready'] else 1
    health(base, model)
    binary = direct.find_claude()
    if not binary:
        raise ValueError('Claude Code가 설치되어 있지 않습니다.')
    project = args.project.expanduser().resolve() if args.project else direct.select_project() if args.choose_project else Path.cwd()
    if not project.is_dir():
        raise ValueError(f'프로젝트 폴더가 없습니다: {project}')
    direct.validate_tool_selection(extra, read_json(home/'.claude.json', {}).get('mcpServers', {}))
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(('ANTHROPIC_', 'STRATA_CUA_TASK_')) or name in (
                'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_RETRY_WATCHDOG',
                'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY'):
            env.pop(name, None)
    return subprocess.call([str(binary), *extra], cwd=project, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Claude Code + OpenCodex: {error}', file=sys.stderr)
        raise SystemExit(1)
