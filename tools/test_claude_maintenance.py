import io
import json
from pathlib import Path
import subprocess
import sys
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from tools.claude_maintenance import MaintenanceTools, MaintenanceMcp, ToolError, ControlRejected
from tools.strata_server_supervisor import Supervisor, control_handler


FIXTURE = '''
from http.server import BaseHTTPRequestHandler,HTTPServer
import json,sys
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.headers.get('Authorization')!='Bearer fixture-key':self.send_error(401);return
  data={'/health':{'status':'ok','loaded':True},'/v1/models':{'data':[{'id':'fixture'}]},'/slots':[{'is_processing':False}]}[self.path]
  raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.token = self.root/'token';self.token.write_text('a'*64)
        self.tools = MaintenanceTools('http://127.0.0.1:8768', self.token, home=self.root)
        self.server = MaintenanceMcp(self.tools, io.BytesIO())

    def call(self, name, args=None, rid=1):
        return self.server.handle({'jsonrpc':'2.0','id':rid,'method':'tools/call','params':{'name':name,'arguments':args or {}}})

    def test_remote_control_and_unknown_arguments_are_rejected(self):
        with self.assertRaises(ValueError):MaintenanceTools('http://example.com',self.token)
        with patch.object(self.tools,'post') as post:
            response = self.call('restart_strata',{'operation_id':'one','checkpoint':'saved','shell':'kill'})
            self.assertTrue(response['result']['isError']);post.assert_not_called()

    def test_mcp_identity_and_only_existing_owner_tools_are_exposed(self):
        response = self.server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
        self.assertEqual(response['result']['serverInfo']['name'],'strata-maintenance')
        self.assertEqual(response['result']['serverInfo']['version'],'1.3.0')
        self.assertEqual({d['name'] for d in self.tools.defs()}, {
            'environment_status','opencodex_service_status','restart_strata','restart_status','cancel_restart',
            'restart_desktop','desktop_restart_status','cancel_desktop_restart','acknowledge_desktop_restart'})
        environment = next(d for d in self.tools.defs() if d['name'] == 'environment_status')
        self.assertEqual(set(environment['inputSchema']['properties']),
                         {'include_opencodex_requests', 'request_window'})
        self.assertEqual(environment['inputSchema']['required'], [])

    def test_opencodex_status_without_registered_owner_is_read_only(self):
        with patch('tools.claude_maintenance.subprocess.run') as run:
            result = self.call('opencodex_service_status')['result']['structuredContent']
        self.assertEqual(result['status'], 'not_configured')
        self.assertFalse(result['ready'])
        run.assert_not_called()

    def test_environment_status_includes_bounded_strata_activity(self):
        activity = {'status':'idle','is_idle':True,'slot_count':1,'busy_slots':0,
                    'scope':'Strata slots only'}
        runtime = {'status':'observed','machine':{'gpu':{'used_mib':23000,'total_mib':24576}},
                   'scope':'GPU snapshot'}
        pacing = {'status':'not_tracking','enabled':False,'queued':0,'in_flight':None}
        effort = {'saved_default':'medium','status':'configured','runtime_status':'not_verified'}
        with patch('tools.claude_maintenance.subprocess.Popen') as log_query, \
                patch('tools.claude_maintenance.shared.diagnose',
                   return_value={'ready':True,'opencodex_request_pacing':pacing,
                                 'host_memory':{'status':'observed','total_mib':131072,'available_mib':24576},
                                 'effort_level':effort}), \
                patch('tools.claude_maintenance.shared.strata_runtime_status', return_value=runtime) as status_call, \
                patch('tools.claude_maintenance.shared.strata_activity', return_value=activity) as activity_call:
            result = self.call('environment_status')['result']['structuredContent']
        self.assertTrue(result['ready'])
        self.assertEqual(result['strata_activity'], activity)
        self.assertEqual(result['strata_runtime'], runtime)
        self.assertEqual(result['opencodex_request_pacing'], pacing)
        self.assertEqual(result['host_memory']['available_mib'], 24576)
        self.assertEqual(result['effort_level'], effort)
        status_call.assert_called_once_with(self.root, timeout=1)
        self.assertEqual(activity_call.call_args.args, (self.root,))
        self.assertEqual(activity_call.call_args.kwargs['runtime_status'], runtime)
        self.assertGreater(activity_call.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(activity_call.call_args.kwargs['timeout'], 3)
        log_query.assert_not_called()

    def test_environment_status_opt_in_returns_only_sanitized_recent_opencodex_fields(self):
        owner_home = self.root/'.opencodex'; owner_home.mkdir()
        bun = self.root/'bun.exe'; bun.write_bytes(b'fixture')
        cli = self.root/'index.ts'; cli.write_bytes(b'fixture')
        codex_home = self.root/'.codex'
        (owner_home/'service-state.json').write_text(json.dumps({
            'bunPath':str(bun),'cliPath':str(cli),'opencodexHome':str(owner_home),
            'codexHome':str(codex_home)}),encoding='utf-8')
        payload = {'schemaVersion':1,'window':{'scanLimit':2000,'loaded':20,'matched':2,'returned':1,'limit':12},
            'cursor':'private-cursor','logs':[{'requestId':'private-request','conversationId':'private-conversation',
                'prompt':'private prompt','response':'private response','requestedEffort':'HIGH','status':200,
                'durationMs':4500,'firstOutputMs':40,'genStartMs':800,'lastOutputMs':4480,
                'closeReason':'terminal','terminalStatus':'private unknown enum',
                'usage':{'inputTokens':12000,'cacheReadInputTokens':11000,'outputTokens':400,
                         'totalTokens':12400,'secret':'private usage'},
                'protocolTrace':{'body':'private trace'}}]}
        class FixtureProcess:
            def __init__(self, data):
                self.stdout = io.BytesIO(data)
                self.returncode = 0
                self.killed = False
            def wait(self, timeout=None):
                return self.returncode
            def kill(self):
                self.killed = True
                self.returncode = -9
        process = FixtureProcess(json.dumps(payload).encode())
        with patch('tools.claude_maintenance.subprocess.Popen',return_value=process) as run:
            with patch('tools.claude_maintenance.shared.diagnose',return_value={'ready':True}), \
                    patch('tools.claude_maintenance.shared.strata_runtime_status',return_value={'status':'ok'}), \
                    patch('tools.claude_maintenance.shared.strata_activity',return_value={'status':'idle'}):
                result = self.call('environment_status',{
                    'include_opencodex_requests':True,'request_window':'1h'})['result']['structuredContent']
        report = result['opencodex_recent_requests']
        self.assertEqual(report['status'],'observed')
        self.assertEqual(report['window_counts'],{'loaded':20,'matched':2,'returned':1,'limit':12})
        row = report['requests'][0]
        self.assertEqual(row['requested_effort'],'high')
        self.assertEqual(row['http_status'],200)
        self.assertEqual(row['duration_ms'],4500)
        self.assertEqual(row['message_stop_evidence'],'not_recorded')
        self.assertNotIn('terminal_status',row)
        self.assertEqual(row['usage'],{'input_tokens':12000,'cache_read_input_tokens':11000,
            'output_tokens':400,'total_tokens':12400})
        serialized = json.dumps(report)
        for private in ('private-request','private-conversation','private prompt','private response',
                        'private-cursor','private trace','private usage','private stderr'):
            self.assertNotIn(private,serialized)
        self.assertEqual(run.call_args.args[0],[str(bun),str(cli),'logs','filter','--surface','claude',
            '--time-window','1h','--limit','12','--json'])
        self.assertEqual(run.call_args.kwargs['stdin'],subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['stdout'],subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs['stderr'],subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['bufsize'],0)
        self.assertEqual(run.call_args.kwargs['env']['OPENCODEX_HOME'],str(owner_home))
        self.assertEqual(run.call_args.kwargs['env']['CODEX_HOME'],str(codex_home))

    def test_environment_status_request_log_reader_stops_at_128_kib(self):
        owner_home = self.root/'.opencodex'; owner_home.mkdir()
        bun = self.root/'bun.exe'; bun.write_bytes(b'fixture')
        cli = self.root/'index.ts'; cli.write_bytes(b'fixture')
        (owner_home/'service-state.json').write_text(json.dumps({
            'bunPath':str(bun),'cliPath':str(cli),'opencodexHome':str(owner_home)}),encoding='utf-8')
        class FixtureProcess:
            def __init__(self, data):
                self.stdout = io.BytesIO(data)
                self.returncode = 0
                self.killed = False
            def wait(self, timeout=None):
                return self.returncode
            def kill(self):
                self.killed = True
                self.returncode = -9
        process = FixtureProcess(b'x'*(128*1024+4096))
        with patch('tools.claude_maintenance.subprocess.Popen',return_value=process):
            report = self.tools.opencodex_recent_requests('15m')
        self.assertEqual(report['status'],'invalid_status_response')
        self.assertEqual(report['requests'],[])
        self.assertTrue(process.killed)

    def test_environment_status_request_logs_are_opt_in_and_validate_window(self):
        with patch('tools.claude_maintenance.subprocess.Popen') as run, \
                patch('tools.claude_maintenance.shared.diagnose',return_value={'ready':True}), \
                patch('tools.claude_maintenance.shared.strata_runtime_status',return_value={'status':'ok'}), \
                patch('tools.claude_maintenance.shared.strata_activity',return_value={'status':'idle'}):
            result = self.call('environment_status',{
                'include_opencodex_requests':True,'request_window':'24h'})
        self.assertTrue(result['result']['isError'])
        run.assert_not_called()

    def test_environment_status_opt_in_without_owner_reports_unavailable_without_running_cli(self):
        with patch('tools.claude_maintenance.subprocess.Popen') as run, \
                patch('tools.claude_maintenance.shared.diagnose',return_value={'ready':True}), \
                patch('tools.claude_maintenance.shared.strata_runtime_status',return_value={'status':'ok'}), \
                patch('tools.claude_maintenance.shared.strata_activity',return_value={'status':'idle'}):
            result = self.call('environment_status',{'include_opencodex_requests':True})['result']['structuredContent']
        self.assertEqual(result['opencodex_recent_requests']['status'],'not_configured')
        self.assertEqual(result['opencodex_recent_requests']['requests'],[])
        run.assert_not_called()

    def test_opencodex_status_uses_recorded_owner_and_redacts_runtime_secrets(self):
        owner_home = self.root/'.opencodex'
        owner_home.mkdir()
        bun = self.root/'bun.exe'; bun.write_text('fixture')
        cli = self.root/'index.ts'; cli.write_text('fixture')
        (owner_home/'service-state.json').write_text(json.dumps({
            'backend':'scheduler','opencodexHome':str(owner_home),
            'bunPath':str(bun),'cliPath':str(cli),'codexHome':str(self.root/'.codex')}),encoding='utf-8')
        (owner_home/'runtime-port.json').write_text(json.dumps({
            'pid':4242,'port':10100,'attestationSecret':'fixture-secret'}),encoding='utf-8')
        (owner_home/'serving-runtimes.json').write_text(json.dumps({'runtimes':[
            {'version':'2.92.0','servedAt':'2026-10-26T12:00:00Z'}]}),encoding='utf-8')
        status = {'schemaVersion':1,'platform':'win32','supported':True,'backend':'schtasks',
            'label':'opencodex-proxy','installed':True,'enabled':True,'running':True,'viable':True,
            'stale':False,'conflict':False,'serving':{'probed':True,'ok':True,'port':10100},
            'summary':'fixture summary','logPath':str(self.root/'service.log'),
            'ownershipLease':'private-value'}
        completed = subprocess.CompletedProcess([],0,json.dumps(status),'fixture-secret-on-stderr')
        with patch('tools.claude_maintenance.subprocess.run',return_value=completed) as run:
            result = self.call('opencodex_service_status')['result']['structuredContent']
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['runtime_identity'],{'pid':4242,'runtimes':[
            {'version':'2.92.0','served_at':'2026-10-26T12:00:00Z'}]})
        self.assertEqual(result['restart_command'],[str(bun),str(cli),'service','restart'])
        serialized=json.dumps(result)
        self.assertNotIn('fixture-secret',serialized)
        self.assertNotIn('ownershipLease',serialized)
        self.assertNotIn('logPath',serialized)
        self.assertEqual(run.call_args.args[0],[str(bun),str(cli),'service','status','--json'])
        self.assertEqual(run.call_args.kwargs['env']['OPENCODEX_HOME'],str(owner_home))
        self.assertEqual(run.call_args.kwargs['stderr'],subprocess.DEVNULL)

    def test_opencodex_status_never_falls_back_to_path_or_runs_unowned_files(self):
        owner_home = self.root/'.opencodex'; owner_home.mkdir()
        (owner_home/'service-state.json').write_text(json.dumps({
            'backend':'scheduler','bunPath':'bun','cliPath':'opencodex'}),encoding='utf-8')
        with patch('tools.claude_maintenance.subprocess.run') as run:
            result = self.call('opencodex_service_status')['result']['structuredContent']
        self.assertEqual(result['status'],'invalid_owner_state')
        run.assert_not_called()

    def test_uncertain_delivery_attempts_cancel_with_same_id_and_returns_tool_error(self):
        calls=[]
        def fail(route, body):
            calls.append((route,body))
            if route=='/restart':raise OSError('fixture lost response')
            return {'cancelled':True}
        with patch.object(self.tools,'post',side_effect=fail):
            response=self.call('restart_strata',{'operation_id':'one','checkpoint':'saved'})
        self.assertTrue(response['result']['isError'])
        self.assertEqual([route for route,_ in calls],['/restart','/cancel'])
        self.assertTrue(all(body['operation_id']=='one' for _,body in calls))

    def test_cancel_notification_interrupts_active_restart_and_receipt_inspection_is_read_only(self):
        entered=threading.Event();calls=[]
        def post(route,body):
            calls.append(route)
            if route=='/restart':entered.set()
            return {'operation_id':'one','state':'queued'} if route!='/cancel' else {'cancelled':True}
        output=[]
        with patch.object(self.tools,'post',side_effect=post):
            worker=threading.Thread(target=lambda:output.append(self.call('restart_strata',{'operation_id':'one','checkpoint':'saved'},11)))
            worker.start();self.assertTrue(entered.wait(2))
            self.server.handle({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':11}})
            worker.join(3)
            self.assertFalse(worker.is_alive());self.assertTrue(output[0]['result']['isError'])
            self.assertIn('/cancel',calls)
            calls.clear();self.call('restart_status',{'operation_id':'one'})
            self.assertEqual(calls,['/status'])

    def test_cancel_before_worker_registration_never_submits(self):
        self.server.handle({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':12}})
        with patch.object(self.tools,'post') as post:
            result=self.call('restart_strata',{'operation_id':'one','checkpoint':'saved'},12)
            self.assertTrue(result['result']['isError']);post.assert_not_called()

    def test_duplicate_active_id_is_not_dispatched_and_original_keeps_cancellation(self):
        entered, release = threading.Event(), threading.Event()
        owners, output = [], []
        def call(name, args):
            owners.append(self.tools.local.cancelled)
            if len(owners) == 1:
                entered.set()
                release.wait(3)
            return {'fixture': 'complete'}
        with patch.object(self.tools, 'call', side_effect=call) as dispatch:
            worker = threading.Thread(target=lambda: output.append(self.call('environment_status', rid=11)))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                duplicate = self.call('environment_status', rid=11)
                tracked = self.server.active.get(11)
                self.server.handle({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':11}})
                was_cancelled = owners[0].is_set()
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(dispatch.call_count, 1)
        self.assertIn('duplicate active', duplicate['error']['message'])
        self.assertIs(tracked, owners[0])
        self.assertTrue(was_cancelled)
        self.assertEqual(self.server.active, {})
        self.assertEqual(self.server.explicit_active, {})

    def test_completed_id_can_be_reused_for_a_new_observation(self):
        with patch.object(self.tools, 'call', return_value={'fixture':'complete'}) as dispatch:
            for _ in range(2):
                self.assertFalse(self.call('environment_status', rid=11)['result']['isError'])
        self.assertEqual(dispatch.call_count, 2)

    def test_malformed_cancel_envelope_cannot_cancel_active_work(self):
        entered, release = threading.Event(), threading.Event()
        state, output = {}, []
        def call(name, args):
            state['cancelled'] = self.tools.local.cancelled
            state['explicit'] = self.tools.local.explicit_cancelled
            entered.set()
            release.wait(3)
            return {'fixture':'complete'}
        with patch.object(self.tools, 'call', side_effect=call):
            worker = threading.Thread(target=lambda: output.append(self.call('environment_status', rid=11)))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                observations = []
                for message in (
                    {'jsonrpc':'invalid','method':'notifications/cancelled','params':{'requestId':11}},
                    {'jsonrpc':'2.0','id':99,'method':'notifications/cancelled','params':{'requestId':11}},
                ):
                    self.server.handle(message)
                    observations.append(state['cancelled'].is_set())
                self.server.handle({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':11}})
                valid_cancelled = state['cancelled'].is_set() and state['explicit'].is_set()
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(observations, [False, False])
        self.assertTrue(valid_cancelled)

    def test_invalid_request_ids_never_dispatch_or_break_cancellation(self):
        with patch.object(self.tools, 'call', return_value={'fixture':'complete'}) as dispatch:
            for rid in ([], {}, None, True):
                with self.subTest(rid=rid):
                    response = self.call('environment_status', rid=rid)
                    self.assertIn('error', response)
                    self.server.handle({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':rid}})
        dispatch.assert_not_called()

    def test_eof_cancels_before_late_worker_submission(self):
        self.server.serve(io.BytesIO(b''))
        with patch.object(self.tools,'post') as post:
            result=self.call('restart_strata',{'operation_id':'one','checkpoint':'saved'})
            self.assertTrue(result['result']['isError']);post.assert_not_called()

    def test_failed_or_mismatched_ready_receipt_never_reports_success(self):
        for receipt in [{'operation_id':'one','state':'failed'}, {'operation_id':'other','state':'ready'},
                        {'operation_id':'one','state':'ready','cancelled':True}]:
            with self.subTest(receipt=receipt),patch.object(self.tools,'post',return_value=receipt):
                self.assertTrue(self.call('restart_strata',{'operation_id':'one','checkpoint':'saved'})['result']['isError'])

    def test_known_rejection_never_cancels_an_existing_operation_with_same_id(self):
        with patch.object(self.tools,'post',side_effect=ControlRejected('fixture rejected duplicate checkpoint')) as post:
            self.assertTrue(self.call('restart_strata',{'operation_id':'one','checkpoint':'different'})['result']['isError'])
            self.assertEqual(post.call_count,1)
            self.assertEqual(post.call_args.args[0],'/restart')

    def test_timeout_and_invalid_token_do_not_silently_succeed(self):
        with patch.object(self.tools,'post',return_value={'operation_id':'one','state':'starting'}):
            self.assertTrue(self.call('restart_strata',{'operation_id':'one','checkpoint':'saved','timeout_seconds':1})['result']['isError'])
        self.token.write_text('not-a-token')
        with patch.object(self.tools.opener,'open') as opener:
            self.assertTrue(self.call('restart_status',{'operation_id':'one'})['result']['isError']);opener.assert_not_called()


class SupervisorAdapterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        fixture=self.root/'server.py';fixture.write_text(FIXTURE)
        key=self.root/'api-key';key.write_text('fixture-key')
        token=self.root/'token';token.write_text('a'*64)
        port=free_port()
        self.supervisor=Supervisor(self.root,[sys.executable,str(fixture),str(port)],f'http://127.0.0.1:{port}',key,'fixture',ready_timeout=5)
        self.control=ThreadingHTTPServer(('127.0.0.1',0),control_handler(self.supervisor,'a'*64))
        self.thread=threading.Thread(target=self.control.serve_forever,daemon=True);self.thread.start()
        self.tools=MaintenanceTools('http://127.0.0.1:'+str(self.control.server_port),token)

    def tearDown(self):
        self.control.shutdown();self.control.server_close()
        if self.supervisor.worker:self.supervisor.worker.join(10)
        self.supervisor.stopping.set();self.supervisor.process.stop();self.supervisor.log.close();self.temp.cleanup()

    def test_existing_owned_child_restart_repeated_id_and_followup_readiness(self):
        self.supervisor.start();old=self.supervisor.process.child.pid
        result=self.tools.call('restart_strata',{'operation_id':'one','checkpoint':'saved fixture; remaining: readiness','timeout_seconds':10})
        self.assertEqual(result['state'],'ready');self.assertNotEqual(old,self.supervisor.process.child.pid)
        pid=self.supervisor.process.child.pid
        self.assertEqual(self.tools.call('restart_strata',{'operation_id':'one','checkpoint':'saved fixture; remaining: readiness','timeout_seconds':10})['state'],'ready')
        self.assertEqual(pid,self.supervisor.process.child.pid)
        self.assertEqual(self.supervisor.api('/health')['status'],'ok')
        with self.assertRaises(ControlRejected):
            self.tools.call('restart_strata',{'operation_id':'one','checkpoint':'different checkpoint','timeout_seconds':10})
        self.assertFalse(self.supervisor.snapshot()['cancelled'])
        self.assertEqual(pid,self.supervisor.process.child.pid)

    def test_busy_server_is_not_stopped(self):
        with patch.object(self.supervisor,'api',return_value=[{'is_processing':True}]),patch.object(self.supervisor.process,'stop') as stop:
            with self.assertRaisesRegex(ToolError,'timed out'):
                self.tools.call('restart_strata',{'operation_id':'busy','checkpoint':'saved; server busy','timeout_seconds':1})
            self.supervisor.worker.join(3)
            self.assertEqual(self.supervisor.snapshot()['state'],'cancelled')
            stop.assert_not_called()


if __name__=='__main__':unittest.main()
