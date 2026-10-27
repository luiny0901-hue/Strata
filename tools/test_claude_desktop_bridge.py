import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.claude_maintenance import MaintenanceMcp, MaintenanceTools, ControlRejected
from tools.strata_server_supervisor import control_handler, OwnedProcess


SESSION = 'e4f55f01-b180-46db-9423-638e43393c32'


class McpDesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = MaintenanceTools('http://127.0.0.1:8768', self.root/'token', home=self.root)
        self.server = MaintenanceMcp(self.tools, io.BytesIO())
        self.args = {'operation_id': 'desktop-one', 'session_id': SESSION,
                     'checkpoint_path': str(self.root/'CHECKPOINT.md')}

    def call(self, name='restart_desktop', args=None):
        return self.server.handle({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                  'params': {'name': name, 'arguments': self.args if args is None else args}})

    def test_submission_uses_actual_mcp_pid_and_rejects_model_supplied_commands(self):
        with patch.object(self.tools, 'post', return_value={'operation_id': 'desktop-one', 'state': 'queued'}) as post:
            result = self.call()
            self.assertFalse(result['result']['isError'])
            self.assertEqual(post.call_args.args, ('/desktop/restart', {**self.args, 'caller_pid': os.getpid()}))
            invalid = self.call(args={**self.args, 'command': 'anything'})
            self.assertTrue(invalid['result']['isError'])
            self.assertEqual(post.call_count, 1)

    def test_owner_eof_after_submission_does_not_cancel_the_external_handoff(self):
        def post(route, body):
            self.server.closing.set()
            self.tools.local.cancelled.set()
            return {'operation_id': 'desktop-one', 'state': 'queued'}
        with patch.object(self.tools, 'post', side_effect=post) as mocked:
            result = self.call()
        self.assertFalse(result['result']['isError'])
        self.assertEqual(mocked.call_count, 1)

    def test_explicit_stop_during_submission_cancels_the_same_operation(self):
        def post(route, body):
            if route == '/desktop/restart':
                self.server.handle({'jsonrpc': '2.0', 'method': 'notifications/cancelled',
                                    'params': {'requestId': 7}})
                return {'operation_id': 'desktop-one', 'state': 'queued'}
            return {'operation_id': 'desktop-one', 'state': 'cancelled'}
        with patch.object(self.tools, 'post', side_effect=post) as mocked:
            result = self.call()
        self.assertTrue(result['result']['isError'])
        self.assertEqual([call.args[0] for call in mocked.call_args_list], ['/desktop/restart', '/desktop/cancel'])
        self.assertEqual(mocked.call_args_list[-1].args[1], {'operation_id': 'desktop-one'})

    def test_stop_before_submission_records_cancel_but_never_restarts(self):
        self.server.handle({'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 7}})
        with patch.object(self.tools, 'post', return_value={'state': 'cancelled'}) as post:
            result = self.call()
        self.assertTrue(result['result']['isError'])
        post.assert_called_once_with('/desktop/cancel', {'operation_id': 'desktop-one'})

    def test_rejected_request_does_not_cancel_an_older_transaction(self):
        def post(route, body):
            self.server.handle({'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 7}})
            raise ControlRejected('operation belongs to a different checkpoint')
        with patch.object(self.tools, 'post', side_effect=post) as mocked:
            self.assertTrue(self.call()['result']['isError'])
        self.assertEqual(mocked.call_count, 1)

    def test_status_and_ack_routes_never_resubmit_a_restart(self):
        with patch.object(self.tools, 'post', return_value={'enabled': True}) as post:
            self.call('desktop_restart_status', {})
            post.assert_called_with('/desktop/capabilities', {})
            self.call('desktop_restart_status', {'operation_id': 'desktop-one'})
            post.assert_called_with('/desktop/status', {'operation_id': 'desktop-one'})
            ack = {'operation_id': 'desktop-one', 'session_id': SESSION, 'nonce': 'c'*32}
            self.call('acknowledge_desktop_restart', ack)
            post.assert_called_with('/desktop/ack', ack)


class DesktopControlHttpTests(unittest.TestCase):
    def setUp(self):
        self.desktop = SimpleNamespace(
            prepare=lambda *args: {'operation_id': args[0], 'state': 'queued', 'accepted': True},
            status=lambda op: {'operation_id': op, 'state': 'waiting_for_handoff'},
            cancel=lambda op: {'operation_id': op, 'state': 'cancelled'},
            acknowledge=lambda op, nonce, session: {'operation_id': op, 'acknowledged': True})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), control_handler(SimpleNamespace(), 'a'*64, self.desktop))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, route, body, token='a'*64):
        request = Request(f'http://127.0.0.1:{self.server.server_port}'+route,
                          data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+token})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_exact_authenticated_control_routes(self):
        self.assertTrue(self.request('/desktop/capabilities', {})['enabled'])
        body = {'operation_id': 'desktop-one', 'session_id': SESSION, 'checkpoint_path': 'saved', 'caller_pid': 12}
        self.assertEqual(self.request('/desktop/restart', body)['state'], 'queued')
        self.assertEqual(self.request('/desktop/status', {'operation_id': 'desktop-one'})['state'], 'waiting_for_handoff')
        with self.assertRaises(HTTPError) as denied:
            self.request('/desktop/capabilities', {}, token='wrong')
        self.assertEqual(denied.exception.code, 401)


class OwnedRecoveryChildTests(unittest.TestCase):
    def test_recovery_child_uses_exact_working_directory_and_clean_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            output = io.BytesIO()
            script = 'import os,json;print(json.dumps({"cwd":os.getcwd(),"child":os.getenv("STRATA_SUPERVISOR_CHILD"),"marker":os.getenv("RECOVERY_FIXTURE")}))'
            env = dict(os.environ, RECOVERY_FIXTURE='owned')
            env.pop('STRATA_SUPERVISOR_CHILD', None)
            child = OwnedProcess([sys.executable, '-c', script], output, cwd=folder, environment=env)
            try:
                child.start()
                child.child.wait(timeout=10)
            finally:
                child.stop(grace_seconds=2)
            result = json.loads(output.getvalue())
            self.assertEqual(Path(result['cwd']).resolve(), Path(folder).resolve())
            self.assertIsNone(result['child'])
            self.assertEqual(result['marker'], 'owned')


if __name__ == '__main__':
    unittest.main()
