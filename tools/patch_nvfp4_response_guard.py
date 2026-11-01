"""Install the opt-in Messages delivery hook without replacing the downloaded fork's server."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.claude_opencodex_client import publish_files

MARKER = '# STRATA_ANTHROPIC_RESPONSE_GUARD_V1'
IMPORT = 'from serve.anthropic_response_guard import configure_response_guard, guard_anthropic_events  '+MARKER
WRAP = ('            events = guard_anthropic_events(events, req, enabled=getattr(svc, "anthropic_response_guard", False),\n'
        '                                            with_tools=bool(tools), cancel=cancel, heartbeat_s=KEEPALIVE_S)  '+MARKER)
CONFIG = '    configure_response_guard(svc, cfg.get("anthropic_response_guard", False))  '+MARKER
ERROR = '''            except StructuredOutputError as e:  # STRATA_ANTHROPIC_RESPONSE_GUARD_V1
                err = {"type": "error", "error": {"type": "api_error", "code": "structured_output_failed", "message": str(e)}}
                self._note(error=err["error"])
                self.wfile.write(b"event: error\\ndata: " + json.dumps(err).encode() + b"\\n\\n")
'''
CHANGES = (
    ('from serve.structured import StructuredOutputError, prepare_format, validated_json  # noqa: E402',
     'from serve.structured import StructuredOutputError, prepare_format, validated_json  # noqa: E402\n'+IMPORT),
    ('            events = anthropic_events(svc, req, ids, thinking, tools, max_new, cancel, force=force)',
     '            events = anthropic_events(svc, req, ids, thinking, tools, max_new, cancel, force=force)\n'+WRAP),
    ('    recovery = cfg.get("reasoning_loop_recovery", False)',
     CONFIG+'\n    recovery = cfg.get("reasoning_loop_recovery", False)'),
    ('            except EngineDied as e:                          # mid-stream: Anthropic\'s error event',
     ERROR+'            except EngineDied as e:                          # mid-stream: Anthropic\'s error event'),
)


class PatchError(ValueError):
    pass


def patch_server(source):
    if MARKER in source:
        if source.count(MARKER)!=4 or not all(part in source for part in (IMPORT,WRAP,CONFIG,ERROR)):
            raise PatchError('partial response-guard hook; preserve and inspect the fork before editing')
        return source
    counts=[source.count(old) for old,_ in CHANGES]
    if counts!=[1]*len(CHANGES):
        raise PatchError(f'unknown server layout; expected one of each hook, found {counts}')
    for old,new in CHANGES: source=source.replace(old,new,1)
    return source


def patch_structured(source):
    changes=(('def validated_json(text, validator, finish):',
              'def validated_json(text, validator, finish, *, extractor=None):'),
             ('value = json.loads(_extract_json(text), object_pairs_hook=pairs, parse_constant=constant)',
              'value = json.loads((extractor or _extract_json)(text), object_pairs_hook=pairs, parse_constant=constant)'))
    if all(new in source for _,new in changes): return source
    if any(new in source for _,new in changes) or any(source.count(old)!=1 for old,_ in changes):
        raise PatchError('unknown or partial structured-output helper; preserve it before editing')
    for old,new in changes: source=source.replace(old,new,1)
    return source


def install(server, module=None):
    server=Path(server).resolve()
    module=Path(module or ROOT/'serve/anthropic_response_guard.py').resolve()
    structured=server.with_name('structured.py')
    destination=server.with_name('anthropic_response_guard.py')
    before={p:p.read_bytes() if p.exists() else None for p in (server,structured,destination)}
    files={}
    for path,patch in [(server,patch_server),(structured,patch_structured)]:
        original=before[path]
        if original is None: raise PatchError(f'required source is missing: {path.name}')
        text=original.decode('utf-8-sig');newline='\r\n' if '\r\n' in text else '\n'
        result=patch(text.replace('\r\n','\n'))
        compile(result,str(path),'exec')
        files[path]=('\ufeff' if original.startswith(b'\xef\xbb\xbf') else '')+result.replace('\n',newline)
    payload=module.read_bytes().decode('utf-8-sig')
    compile(payload,str(destination),'exec')
    files[destination]=payload
    backup,changed=publish_files(files,server.parent/'.response-guard',before)
    return {'changed':changed,'backup':str(backup) if backup else None}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('server',type=Path)
    p.add_argument('--module',type=Path);args=p.parse_args()
    try: result=install(args.server,args.module)
    except (OSError,UnicodeError,ValueError,SyntaxError) as e:
        print('[strata] cannot install Messages response guard: '+str(e),file=sys.stderr);return 2
    print('[strata] Messages response guard integration ready; changed files='+str(result['changed']))
    return 0


if __name__=='__main__':raise SystemExit(main())
