"""CPU transport checks: thought filtering must preserve reports and input."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import importlib.util
import os


class CompactDisplay(unittest.TestCase):
    def test_approval_response_publish_is_complete_and_retries_only_control_file(self):
        source = Path(__file__).parent / 'opencode/acp_compact_display.py'
        spec = importlib.util.spec_from_file_location('approval_atomic_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'approval.response'
            file.write_text('{"accepted":false}')
            attempts = []
            def replace(first, second):
                self.assertEqual(json.loads(file.read_text()), {'accepted':False})
                self.assertEqual(json.loads(Path(first).read_text()), {'accepted':True})
                attempts.append(1)
                if len(attempts) == 1:
                    raise PermissionError('reader lock')
                os.replace(first, second)
            module.atomic_json(file, {'accepted':True}, replace)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(json.loads(file.read_text()), {'accepted':True})
            self.assertFalse(file.with_suffix('.response.pending').exists())

    def test_transient_windows_replace_lock_does_not_end_transport(self):
        source = Path(__file__).parent / 'opencode/acp_compact_display.py'
        spec = importlib.util.spec_from_file_location('display_lock_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            attempts = []
            def replace(first, second):
                attempts.append(1)
                if len(attempts) in (1, 2):
                    raise PermissionError('simulated Windows reader lock')
                return os.replace(first, second)
            state = module.TaskState(Path(directory)/'tasks.json', replace=replace)
            self.assertEqual(len(attempts), 3)
            state.incoming({'id':1,'method':'session/prompt','params':{'sessionId':'a'}})
            self.assertEqual(len(json.loads(state.path.read_text())['tasks']), 1)
            state.close()

    def test_task_boundaries(self):
        source = Path(__file__).parent / 'opencode/acp_compact_display.py'
        spec = importlib.util.spec_from_file_location('display_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'tasks.json'
            state = module.TaskState(file)
            state.incoming({'id': 1, 'method': 'session/prompt', 'params': {'sessionId': 'a'}})
            first = json.loads(file.read_text())['tasks'][0]['key']
            state.outgoing({'id': 9, 'result': {}})  # Permission/other RPC replies are not completion.
            self.assertEqual(len(json.loads(file.read_text())['tasks']), 1)
            state.outgoing({'id': 1, 'result': {'stopReason': 'end_turn'}})
            self.assertEqual(json.loads(file.read_text())['tasks'], [])
            state.incoming({'id': 2, 'method': 'session/prompt', 'params': {'sessionId': 'a'}})
            self.assertNotEqual(json.loads(file.read_text())['tasks'][0]['key'], first)
            state.incoming({'method': 'session/cancel', 'params': {'sessionId': 'a'}})
            self.assertEqual(json.loads(file.read_text())['tasks'], [])
            state.incoming({'id': 3, 'method': 'session/prompt', 'params': {'sessionId': 'b'}})
            state.close()
            self.assertEqual(json.loads(file.read_text())['tasks'], [])
            state.close()  # Late stdin EOF after cleanup is harmless.

    def test_live_task_state_forwarding(self):
        proxy = Path(__file__).parent / 'opencode/acp_compact_display.py'
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / 'child.py'
            child.write_text('''import json,sys,os
from pathlib import Path
file=Path(os.environ['STRATA_CUA_TASK_STATE'])
for line in sys.stdin.buffer:
    msg=json.loads(line)
    print(json.dumps({'id':msg['id'],'result':{'state':json.loads(file.read_text()),'path':str(file)}}),flush=True)
''', encoding='utf-8')
            process = subprocess.Popen([sys.executable, str(proxy), '--', sys.executable, str(child)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                def request(number):
                    process.stdin.write((json.dumps({'id':number,'method':'session/prompt','params':{'sessionId':'test'}})+'\n').encode())
                    process.stdin.flush()
                    return json.loads(process.stdout.readline())['result']
                first = request(1)
                self.assertEqual(first['state']['tasks'][0]['sessionID'], 'test')
                self.assertEqual(json.loads(Path(first['path']).read_text())['tasks'], [])
                second = request(2)
                self.assertNotEqual(first['state']['tasks'][0]['key'], second['state']['tasks'][0]['key'])
                process.stdin.close()
                self.assertEqual(process.wait(timeout=10), 0)
                self.assertFalse(Path(first['path']).exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()

    def test_transport(self):
        proxy = Path(__file__).parent / 'opencode/acp_compact_display.py'
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / 'child.py'
            child.write_text('''import json,sys
for line in sys.stdin.buffer:
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()
for kind in ['agent_thought_chunk','agent_message_chunk','tool_call_update']:
    print(json.dumps({'method':'session/update','params':{'update':{'sessionUpdate':kind,'content':{'type':'text','text':'FINAL_REPORT'}}}}),flush=True)
print(json.dumps({'id':7,'result':{'stopReason':'end_turn'}}),flush=True)
sys.exit(7)
''', encoding='utf-8')
            lines = [
                {'method':'session/cancel','params':{'sessionId':'test'}},
                {'id':4,'result':{'outcome':{'outcome':'selected','optionId':'allow'}}},
                {'method':'session/update','params':{'update':{'sessionUpdate':'agent_message_chunk','content':{'text':'한글 완료 보고'}}}},
            ]
            payload=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in lines).encode()
            result=subprocess.run([sys.executable,str(proxy),'--',sys.executable,str(child)],input=payload,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,7)
            output=[json.loads(x) for x in result.stdout.splitlines()]
            self.assertEqual(output[:3],lines)
            self.assertEqual(len(output),6)
            self.assertEqual(output[-1],{'id':7,'result':{'stopReason':'end_turn'}})
            self.assertNotIn(b'agent_thought_chunk',result.stdout)
            self.assertIn(b'FINAL_REPORT',result.stdout)


if __name__=='__main__':
    unittest.main()
