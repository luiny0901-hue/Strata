"""Wall-clock soak of isolated installed ACP scenarios; no production/GPU service.

Not an evaluation of a real model's coding quality. Preserve every attempt in a
fresh directory and report failures even if a later attempt succeeds.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.strata_server_supervisor import OwnedProcess, publish

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=[
    ('reconnect',['--output-recovery','--reconnect']),
    ('network-once',['--fault','network-once']),
    ('network-down',['--fault','network-down']),
    ('authentication',['--fault','authentication']),
    ('timeout',['--fault','timeout']),
    ('invalid-json',['--fault','invalid-json']),
    ('shell-cancel',['--cancel','--late-resume']),
    ('stream-cancel-ready',['--cancel-stream-ready']),
    ('late-resume',['--late-resume']),
    ('compact-8192',['--auto-compact','--context','8192','--many-files']),
    ('compact-32768',['--auto-compact','--context','32768']),
    ('compact-262144',['--auto-compact','--context','262144']),
    ('fresh-session',['--fresh-session','--many-files']),
    ('owned-server-restart',[]),
]


def resources(process_handle=None):
    result={'threads':threading.active_count()} if process_handle is None else {}
    if os.name=='nt':
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        count=wintypes.DWORD()
        handle=kernel.GetCurrentProcess() if process_handle is None else process_handle
        if kernel.GetProcessHandleCount(handle,ctypes.byref(count)):
            result['handles']=count.value
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
        info=Counters();info.cb=ctypes.sizeof(info)
        psapi=ctypes.WinDLL('psapi',use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(handle,ctypes.byref(info),info.cb):
            result.update(private_bytes=info.private,working_set_bytes=info.working)
    elif process_handle is None and Path('/proc/self/fd').exists():
        result['fds']=len(list(Path('/proc/self/fd').iterdir()))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--duration-seconds',type=int,default=600)
    args=parser.parse_args()
    if not 1<=args.duration_seconds<=3600:
        parser.error('duration-seconds must be 1..3600')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();attempts=[];failures={};cycle=0
    baseline=resources()
    while time.monotonic()-start<args.duration_seconds:
        cycle+=1
        for name,flags in SCENARIOS:
            if time.monotonic()-start>=args.duration_seconds: break
            if failures.get(name,0)>=2: continue
            folder=root/f'{len(attempts)+1:04d}-{name}'
            script='test_server_restart_acp_runtime.py' if name=='owned-server-restart' else 'test_acp_foreground_runtime.py'
            command=[sys.executable,str(ROOT/'tools'/script),'--binary',args.binary,'--output',str(folder),*flags]
            log_path=root/f'{len(attempts)+1:04d}-{name}.log'
            began=time.monotonic()
            outcome={'scenario':name,'cycle':cycle,'output':str(folder)}
            with log_path.open('ab',buffering=0) as log:
                process=OwnedProcess(command,log)
                try:
                    process.start()
                    process.child.wait(timeout=150)
                    outcome['exit_code']=process.child.returncode
                except Exception as error:
                    outcome['error']=type(error).__name__+': '+str(error)
                finally:
                    process.stop()
            outcome.update(seconds=round(time.monotonic()-began,3),resources=resources())
            if outcome.get('exit_code')!=0: failures[name]=failures.get(name,0)+1
            attempts.append(outcome)
            report={'elapsed_seconds':round(time.monotonic()-start,3),'requested_seconds':args.duration_seconds,
                    'baseline_resources':baseline,'attempts':attempts,'failures':failures,
                    'scope':'Windows installed ACP + scripted CPU model; not real GPU/model quality or Rider/Hermes proof'}
            publish(root/'results.json',report)
            print(json.dumps(outcome,ensure_ascii=False),flush=True)
    print(f'SOAK FINISHED: {len(attempts)} attempts, failures={failures}, elapsed={time.monotonic()-start:.1f}s',flush=True)
    return 1 if failures else 0


if __name__=='__main__':
    raise SystemExit(main())
