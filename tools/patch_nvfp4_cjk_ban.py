"""Install the opt-in Han default ban without replacing the downloaded fork's server."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.claude_opencodex_client import publish_files

MARKER = '# STRATA_CJK_BAN_V1'
GUARD_IMPORT = 'from serve.anthropic_response_guard import configure_response_guard, guard_anthropic_events  # STRATA_ANTHROPIC_RESPONSE_GUARD_V1'
RECOVERY = '    recovery = cfg.get("reasoning_loop_recovery", False)   # #728: false (default) | "stop" | "recover" (true)'
IMPORT = 'from serve.cjk_ban import configure_cjk_ban  '+MARKER
CONFIG = '    configure_cjk_ban(svc, cfg.get("ban_cjk_tokens", False))  '+MARKER
# The anchor is the whole recovery line, trailing comment included: both patches
# re-emit the anchor whole, so neither splits the other's anchor pair that sits on
# the two lines above it.
CHANGES = (
    (GUARD_IMPORT,GUARD_IMPORT+'\n'+IMPORT),
    (RECOVERY,RECOVERY+'\n'+CONFIG),
)


class PatchError(ValueError):
    pass


def patch_server(source):
    if MARKER in source:
        if source.count(MARKER)!=2 or not all(part in source for part in (IMPORT,CONFIG)):
            raise PatchError('partial CJK-ban hook; preserve and inspect the fork before editing')
        return source
    counts=[source.count(old) for old,_ in CHANGES]
    if counts!=[1]*len(CHANGES):
        raise PatchError(f'unknown server layout; the response-guard hooks must be installed first, found {counts}')
    for old,new in CHANGES: source=source.replace(old,new,1)
    return source


def install(server, module=None, bias=None):
    server=Path(server).resolve()
    module=Path(module or ROOT/'serve/cjk_ban.py').resolve()
    bias=Path(bias or ROOT/'serve/logit_bias.py').resolve()
    destination=server.with_name('cjk_ban.py')
    bias_destination=server.with_name('logit_bias.py')
    before={p:p.read_bytes() if p.exists() else None for p in (server,bias_destination,destination)}
    files={}
    original=before[server]
    if original is None: raise PatchError(f'required source is missing: {server.name}')
    text=original.decode('utf-8-sig');newline='\r\n' if '\r\n' in text else '\n'
    result=patch_server(text.replace('\r\n','\n'))
    compile(result,str(server),'exec')
    files[server]='﻿' if original.startswith(b'\xef\xbb\xbf') else ''
    files[server]+=result.replace('\n',newline)
    for path,dest in ((module,destination),(bias,bias_destination)):
        payload=path.read_bytes().decode('utf-8-sig')
        compile(payload,str(dest),'exec')
        files[dest]=payload
    backup,changed=publish_files(files,server.parent/'.cjk-ban',before)
    return {'changed':changed,'backup':str(backup) if backup else None}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('server',type=Path)
    p.add_argument('--module',type=Path);p.add_argument('--bias',type=Path)
    args=p.parse_args()
    try: result=install(args.server,args.module,args.bias)
    except (OSError,UnicodeError,ValueError,SyntaxError) as e:
        print('[strata] cannot install the CJK token ban: '+str(e),file=sys.stderr);return 2
    print('[strata] CJK token ban integration ready; changed files='+str(result['changed']))
    return 0


if __name__=='__main__':raise SystemExit(main())
