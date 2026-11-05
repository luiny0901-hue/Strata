"""Sustained single-owner restart/cancel/status/log soak using CPU-only HTTP children."""
import argparse
import ctypes
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
from urllib.request import Request,urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.strata_server_supervisor import Supervisor,BoundedLog,control_handler,publish
from tools.test_strata_server_supervisor import FIXTURE,free_port


def resources(process_handle=None):
    # Moved here from tools/test_autonomy_soak.py when that soak was retired (977b569b);
    # this module is its only consumer.
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
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--duration-seconds',type=int,default=360)
    args=parser.parse_args()
    if not 1<=args.duration_seconds<=3600: parser.error('duration must be 1..3600')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    fixture=root/'fixture.py'
    text=FIXTURE.replace("'is_processing':False","'is_processing':__import__('pathlib').Path(sys.argv[2]).exists()")
    text=text.replace(' def do_GET(self):',' def do_GET(self):\n  print("fixture-output-"*500,flush=True)')
    fixture.write_text(text,encoding='utf-8')
    key=root/'api-key';key.write_text('fixture-key',encoding='utf-8')
    busy=root/'busy';port=free_port()
    supervisor=Supervisor(root,[sys.executable,str(fixture),str(port),str(busy)],f'http://127.0.0.1:{port}',key,'fixture',ready_timeout=10)
    supervisor.log.close();supervisor.log=BoundedLog(root/'server.log',max_bytes=32768,backups=3)
    supervisor.process.log=supervisor.log
    server=ThreadingHTTPServer(('127.0.0.1',0),control_handler(supervisor,'fixture-control'))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    def post(route,body):
        req=Request(f'http://127.0.0.1:{server.server_port}/{route}',data=json.dumps(body).encode(),headers={'Authorization':'Bearer fixture-control','Content-Type':'application/json'})
        with urlopen(req,timeout=5) as response:
            raw=response.read()
        assert len(raw)<1024, 'status unexpectedly contains full checkpoint'
        return json.loads(raw)
    attempts=[];start=time.monotonic();baseline=None;polls=0
    try:
        supervisor.start();thread.start()
        while time.monotonic()-start<args.duration_seconds:
            number=len(attempts)+1;op=f'cycle-{number}';cancel=number%5==0
            began=time.monotonic();pid=supervisor.process.child.pid
            if cancel: busy.write_text('busy')
            body={'operation_id':op,'checkpoint':'Saved source.py; remaining: focused checks. '+ 'x'*15000}
            post('restart',body)
            post('restart',body)  # Same ID/checkpoint must not launch a second transaction.
            if cancel: post('cancel',{'operation_id':op})
            deadline=time.monotonic()+15
            while True:
                result=post('status',{'operation_id':op});polls+=1
                if result['state'] in ('ready','failed','cancelled'): break
                if time.monotonic()>deadline: raise TimeoutError(op)
                time.sleep(.02)
            supervisor.worker.join(timeout=5)
            assert not supervisor.worker.is_alive()
            busy.unlink(missing_ok=True)
            if cancel:
                assert result['state']=='cancelled',result
                assert supervisor.process.child.pid==pid,'cancel before stop changed the server'
            else:
                assert result['state']=='ready',result
                assert supervisor.process.child.pid!=pid,'server process was not replaced'
                post('restart',body)
                assert supervisor.process.child.pid!=pid
            log_bytes=sum(p.stat().st_size for p in root.glob('server.log*'))
            assert log_bytes<=131072,log_bytes
            sample=resources()
            if number==5: baseline=sample
            attempts.append({'cycle':number,'cancelled':cancel,'seconds':round(time.monotonic()-began,3),
                             'resources':sample,'log_bytes':log_bytes})
            report={'elapsed_seconds':round(time.monotonic()-start,3),'requested_seconds':args.duration_seconds,
                    'baseline_after_warmup':baseline,'attempts':attempts,'status_polls':polls,
                    'scope':'One persistent Windows supervisor; owned CPU mock HTTP server, not GPU or GUI'}
            publish(root/'results.json',report)
            if number%20==0: print(json.dumps({'cycles':number,'elapsed':report['elapsed_seconds'],'resources':sample,'log_bytes':log_bytes}),flush=True)
        times=[a['seconds'] for a in attempts if not a['cancelled']]
        print(f'PASS: {len(attempts)} cycles; elapsed={time.monotonic()-start:.1f}s; ready median={statistics.median(times):.3f}s; status polls={polls}',flush=True)
    finally:
        busy.unlink(missing_ok=True)
        supervisor.stopping.set()
        if supervisor.worker: supervisor.worker.join(timeout=15)
        if thread.is_alive():server.shutdown();thread.join()
        server.server_close();supervisor.process.stop();supervisor.log.close()
        assert not supervisor.process.alive()
        assert supervisor.process.output_thread is None or not supervisor.process.output_thread.is_alive()
        publish(root/'cleanup.json',{'owned_process_exited':True,'resources':resources()})


if __name__=='__main__':
    main()
