"""CPU-only lifecycle tests: real owned Python HTTP child; no Strata/GPU or user session."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from tools.strata_server_supervisor import Supervisor, OwnedProcess, BoundedLog, control_handler, owner_lock


FIXTURE = '''
from http.server import BaseHTTPRequestHandler,HTTPServer
import json,sys
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  if self.headers.get('Authorization')!='Bearer fixture-key':
   self.send_error(401);return
  data={'/health':{'status':'ok','loaded':True},'/v1/models':{'data':[{'id':'fixture'}]},'/slots':[{'is_processing':False}]}[self.path]
  raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fixture = self.root/'server.py'
        fixture.write_text(FIXTURE,encoding='utf-8')
        key = self.root/'key'
        key.write_text('fixture-key',encoding='utf-8')
        self.supervisor = Supervisor(self.root,[sys.executable,str(fixture),str(free_port())],
            '',key,'fixture',ready_timeout=5)
        self.supervisor.server_url = 'http://127.0.0.1:'+self.supervisor.process.command[-1]

    def tearDown(self):
        if self.supervisor.worker:
            self.supervisor.worker.join(timeout=10)
        self.supervisor.stopping.set()
        self.supervisor.process.stop()
        self.supervisor.log.close()
        self.temp.cleanup()

    def test_real_owned_child_restart_readiness_and_idempotent_history(self):
        self.supervisor.start()
        old_pid = self.supervisor.process.child.pid
        first=self.supervisor.request('one','Saved source.py; remaining: run focused validation')
        self.assertEqual(first['operation_id'],'one')
        self.supervisor.worker.join(timeout=10)
        self.assertFalse(self.supervisor.worker.is_alive())
        self.assertEqual(self.supervisor.snapshot()['state'],'ready')
        self.assertNotEqual(old_pid,self.supervisor.process.child.pid)
        pid=self.supervisor.process.child.pid
        self.assertEqual(self.supervisor.request('one',first['checkpoint'])['state'],'ready')
        self.assertEqual(self.supervisor.process.child.pid,pid)
        with self.assertRaises(ValueError):
            self.supervisor.request('one','different checkpoint')
        self.supervisor.request('two','another authorized change')
        self.supervisor.worker.join(timeout=10)
        pid=self.supervisor.process.child.pid
        self.assertEqual(self.supervisor.request('one',first['checkpoint'])['state'],'ready')
        self.assertEqual(self.supervisor.process.child.pid,pid)

    @unittest.skipUnless(sys.platform=='win32','Windows BAT execution only')
    def test_windows_bat_launcher_with_spaces_joins_owned_job_before_spawn(self):
        folder=self.root/'launcher with spaces'
        folder.mkdir()
        bat=folder/'server.bat'
        python,script,port=self.supervisor.process.command
        bat.write_bytes(f'@echo off\r\n"{python}" "{script}" {port}\r\nexit /b %ERRORLEVEL%\r\n'.encode())
        self.supervisor.process.command=[str(bat)]
        self.supervisor.start()
        self.supervisor.request('batch','saved; pending verification')
        self.supervisor.worker.join(timeout=10)
        self.assertEqual(self.supervisor.snapshot()['state'],'ready')

    def test_unowned_listener_is_never_adopted_or_stopped(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',int(self.supervisor.process.command[-1])))
            sock.listen()
            with self.assertRaisesRegex(RuntimeError,'occupied'):
                self.supervisor.start()
            self.assertIsNone(self.supervisor.process.child)
            self.assertGreater(sock.fileno(),-1)

    def test_busy_or_unknown_slots_prevent_shutdown(self):
        for slots in ({},[],[{}]):
            with self.subTest(slots=slots), patch.object(self.supervisor,'api',return_value=slots), patch.object(self.supervisor.process,'stop') as stop:
                self.supervisor.request(str(slots),'pending validation')
                self.supervisor.worker.join(timeout=3)
                self.assertEqual(self.supervisor.snapshot()['state'],'failed')
                stop.assert_not_called()

    def test_cancel_before_stop_and_duplicate_active_request(self):
        entered,release=threading.Event(),threading.Event()
        def slots(_):
            entered.set();release.wait(3)
            return [{'is_processing':True}]
        with patch.object(self.supervisor,'api',side_effect=slots), patch.object(self.supervisor.process,'stop') as stop:
            self.supervisor.request('cancel','saved file.py; remaining tests')
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.supervisor.request('cancel','saved file.py; remaining tests')['operation_id'],'cancel')
            with self.assertRaises(ValueError):
                self.supervisor.request('another','different work')
            self.supervisor.cancel('cancel');release.set()
            self.supervisor.worker.join(timeout=3)
            self.assertEqual(self.supervisor.snapshot()['state'],'cancelled')
            stop.assert_not_called()

    def test_startup_timeout_stops_owned_child(self):
        self.supervisor.ready_timeout=0.1
        with patch.object(self.supervisor,'api',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'deadline'):
                self.supervisor.start()
        self.assertFalse(self.supervisor.process.alive())

    def test_cancel_after_stop_restores_service_without_agent_resume(self):
        with patch.object(self.supervisor,'api',return_value=[{'is_processing':False}]), \
             patch.object(self.supervisor,'port_open',return_value=False), \
             patch.object(self.supervisor,'wait_ready'), \
             patch.object(self.supervisor.process,'start') as start, \
             patch.object(self.supervisor.process,'stop',side_effect=lambda:self.supervisor.cancel('restore')):
            self.supervisor.request('restore','saved; do not replay tools')
            self.supervisor.worker.join(timeout=3)
            start.assert_called_once()
            self.assertEqual(self.supervisor.snapshot()['state'],'cancelled')

    def test_shutdown_failure_does_not_start_second_server(self):
        with patch.object(self.supervisor,'api',return_value=[{'is_processing':False}]), \
             patch.object(self.supervisor.process,'stop',side_effect=RuntimeError('drain failed')), \
             patch.object(self.supervisor.process,'start') as start:
            self.supervisor.request('fail-stop','saved pending work')
            self.supervisor.worker.join(timeout=3)
            start.assert_not_called()
            self.assertEqual(self.supervisor.snapshot()['state'],'failed')

    def test_empty_checkpoint_is_rejected(self):
        for checkpoint in ('', '   ', None, 'x'*16001):
            with self.subTest(checkpoint_type=type(checkpoint).__name__),self.assertRaises(ValueError):
                self.supervisor.request('invalid',checkpoint)
        self.assertIsNone(self.supervisor.worker)

    def test_cancel_overtaking_restart_delivery_is_not_lost(self):
        self.supervisor.cancel('late-delivery')
        with self.assertRaisesRegex(ValueError,'cancelled'):
            self.supervisor.request('late-delivery','saved but delivery was uncertain')
        self.assertIsNone(self.supervisor.worker)

    def test_control_authentication_and_request_limits(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),control_handler(self.supervisor,'secret'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for auth,body,expected in [('',b'{}',401),('Bearer secret',b'{}',400)]:
                req=Request(f'http://127.0.0.1:{server.server_port}/restart',data=body,headers={'Authorization':auth})
                with self.assertRaises(HTTPError) as error:
                    urlopen(req,timeout=3)
                self.assertEqual(error.exception.code,expected)
                error.exception.close()
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_control_status_does_not_retransmit_full_checkpoint(self):
        self.supervisor.job={'operation_id':'compact-status','state':'ready','checkpoint':'sensitive saved work '*700,'cancelled':False}
        server=ThreadingHTTPServer(('127.0.0.1',0),control_handler(self.supervisor,'secret'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            req=Request(f'http://127.0.0.1:{server.server_port}/status',data=b'{"operation_id":"compact-status"}',headers={'Authorization':'Bearer secret'})
            with urlopen(req,timeout=3) as response:
                raw=response.read()
            self.assertLess(len(raw),200)
            self.assertNotIn(b'checkpoint',raw)
            self.assertEqual(json.loads(raw)['state'],'ready')
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_snapshot_does_not_serialize_or_expose_mutable_receipt(self):
        self.supervisor.job={'operation_id':'snapshot','state':'ready','checkpoint':'x'*16000,'cancelled':False}
        with patch('tools.strata_server_supervisor.json.dumps',side_effect=AssertionError('unexpected serialization')):
            copy=self.supervisor.snapshot()
        copy['state']='modified by caller'
        self.assertEqual(self.supervisor.job['state'],'ready')

    def test_backend_control_response_has_a_size_limit(self):
        class HugeResponse:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,limit):
                self.limit=limit
                return b'x'*limit
        response=HugeResponse()
        with patch('tools.strata_server_supervisor.urlopen',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'256 KiB'):
                self.supervisor.api('/health')
        self.assertEqual(response.limit,256*1024+1)

    def test_ready_is_not_visible_before_terminal_receipt_is_persisted(self):
        import hashlib
        release=threading.Event()
        original_save=self.supervisor.save
        def delayed_after_save(**values):
            original_save(**values)
            if values.get('state')=='ready':
                release.wait(3)  # Expose scheduling gap between READY and finally.
        receipt=self.root/(hashlib.sha256(b'persist').hexdigest()+'.json')
        with patch.object(self.supervisor,'save',side_effect=delayed_after_save), \
             patch.object(self.supervisor,'api',return_value=[{'is_processing':False}]), \
             patch.object(self.supervisor,'port_open',return_value=False), \
             patch.object(self.supervisor,'wait_ready'), \
             patch.object(self.supervisor.process,'start'), \
             patch.object(self.supervisor.process,'stop'):
            self.supervisor.request('persist','saved; pending verification')
            try:
                deadline=time.monotonic()+2
                while self.supervisor.snapshot()['state']!='ready' and time.monotonic()<deadline:
                    time.sleep(.005)
                self.assertEqual(self.supervisor.snapshot()['state'],'ready')
                self.assertTrue(receipt.exists(),'READY advertised before durable operation receipt')
            finally:
                release.set();self.supervisor.worker.join(timeout=5)
        self.assertEqual(self.supervisor.snapshot()['state'],'ready')

    def test_terminal_persistence_failure_is_not_ready_and_blocks_replay(self):
        from tools.strata_server_supervisor import publish
        def broken_receipt(path,value):
            if path.name!='restart.json' and path.suffix=='.json':
                raise OSError('fixture disk full')
            return publish(path,value)
        with patch('tools.strata_server_supervisor.publish',side_effect=broken_receipt), \
             patch.object(self.supervisor,'api',return_value=[{'is_processing':False}]), \
             patch.object(self.supervisor,'port_open',return_value=False), \
             patch.object(self.supervisor,'wait_ready'), \
             patch.object(self.supervisor.process,'start'), \
             patch.object(self.supervisor.process,'stop'):
            self.supervisor.request('disk-fail','saved; unknown result persistence')
            self.supervisor.worker.join(timeout=5)
        self.assertEqual(self.supervisor.snapshot()['state'],'failed')
        self.assertIsNotNone(self.supervisor.persistence_error)
        with self.assertRaisesRegex(ValueError,'persisted'):
            self.supervisor.request('no-blind-replay','saved')

    def test_worker_start_failure_cannot_leave_queued_work_forever(self):
        with patch('tools.strata_server_supervisor.threading.Thread.start',side_effect=RuntimeError('thread unavailable')):
            with self.assertRaisesRegex(ValueError,'server was not stopped'):
                self.supervisor.request('no-thread','saved')
        self.assertEqual(self.supervisor.snapshot()['state'],'failed')
        self.assertFalse(self.supervisor.transaction_active)
        self.assertIsNone(self.supervisor.worker)

    def test_rotating_log_bounds_large_unbroken_output(self):
        path=self.root/'bounded.log'
        log=BoundedLog(path,max_bytes=1024,backups=3)
        try:
            log.write(b'x'*100000+b'END')
        finally:
            log.close()
        files=list(self.root.glob('bounded.log*'))
        self.assertEqual(len(files),4)
        self.assertLessEqual(sum(file.stat().st_size for file in files),4096)
        self.assertTrue(path.read_bytes().endswith(b'END'))

    def test_oversized_legacy_logs_keep_only_the_newest_bounded_tail(self):
        path=self.root/'legacy.log'
        for file in (path,path.with_name(path.name+'.1')):
            file.write_bytes(b'OLD'*3000+b'NEWEST')
        log=BoundedLog(path,max_bytes=1024,backups=3)
        log.close()
        for file in self.root.glob('legacy.log*'):
            self.assertEqual(file.stat().st_size,1024)
            self.assertTrue(file.read_bytes().endswith(b'NEWEST'))

    def test_owned_output_is_drained_while_child_remains_running(self):
        path=self.root/'live.log'
        with path.open('ab',buffering=0) as log:
            process=OwnedProcess([sys.executable,'-c','import time; print("LIVE_OUTPUT",flush=True);time.sleep(30)'],log)
            try:
                process.start()
                deadline=time.monotonic()+5
                while b'LIVE_OUTPUT' not in path.read_bytes() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertIn(b'LIVE_OUTPUT',path.read_bytes())
                self.assertTrue(process.alive())
            finally:
                process.stop()
            self.assertFalse(process.output_thread.is_alive())

    def test_log_failure_keeps_draining_large_child_output(self):
        class FailedDisk:
            def write(self,_):
                raise OSError('fixture disk full')
        process=OwnedProcess([sys.executable,'-c','import sys;sys.stdout.write("x"*2000000);sys.stdout.flush()'],FailedDisk())
        try:
            process.start()
            process.child.wait(timeout=10)
        finally:
            process.stop()
        self.assertIn('fixture disk full',process.log_error)
        self.assertFalse(process.output_thread.is_alive())

    def test_lock_rejects_second_owner(self):
        with owner_lock(self.root):
            with self.assertRaises(OSError):
                with owner_lock(self.root):
                    self.fail('second owner acquired lock')

    def test_interrupted_transaction_is_recorded_not_replayed(self):
        (self.root/'restart.json').write_text(json.dumps({'operation_id':'old','state':'starting','checkpoint':'saved','checkpoint_hash':'hash'}),encoding='utf-8')
        other=Supervisor(self.root,['unused'],'http://127.0.0.1:1',self.root/'key','fixture')
        try:
            self.assertEqual(other.snapshot()['state'],'failed')
            self.assertIsNone(other.process.child)
        finally:
            other.log.close()

if __name__=='__main__':
    unittest.main()
