"""Opt-in installed OpenCode ACP regression; isolated DB and local mock model."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import sqlite3
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--output-recovery', action='store_true')
    parser.add_argument('--late-resume', action='store_true')
    parser.add_argument('--cancel', action='store_true')
    parser.add_argument('--cancel-stream', action='store_true')
    parser.add_argument('--subagent', action='store_true')
    parser.add_argument('--disconnect', action='store_true')
    parser.add_argument('--fault', choices=['network-once', 'network-down', 'authentication', 'tool-error', 'timeout', 'invalid-json', 'uac', 'powershell-error', 'interactive', 'long-command'])
    parser.add_argument('--auto-compact', action='store_true')
    parser.add_argument('--context', type=int, default=100000)
    parser.add_argument('--reconnect', action='store_true')
    parser.add_argument('--many-files', action='store_true', help='Add 2048 nested unrelated files and verify they are preserved')
    parser.add_argument('--fresh-session', action='store_true', help='Read and edit pre-existing files from a new DB without chat history')
    args = parser.parse_args()
    if args.cancel_stream:
        args.cancel = True
        args.output_recovery = True
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    unrelated = {}
    if args.many_files:
        for index in range(2048):
            file = root / 'fixture-project' / f'module-{index % 32:02d}' / 'nested' / f'file-{index:04d}.txt'
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(f'UNRELATED_{index}\n' * 16, encoding='utf-8')
            unrelated[file] = hashlib.sha256(file.read_bytes()).hexdigest()
    requests = []
    if args.fresh_session:
        (root/'existing.txt').write_text('BEFORE_HISTORY_FREE',encoding='utf-8')
        (root/'unrelated.txt').write_text('KEEP_EXISTING_WORK',encoding='utf-8')
    events = []
    rpc_timings = []
    marker = root / 'must-not-exist.txt'
    plugin = Path(__file__).resolve().parents[1] / 'examples/opencode/acp-foreground-guard'
    signal = root / 'wake.signal'
    fired = root / 'wake-fired.txt'
    started = root / 'shell-started.txt'
    after_cancel = root / 'after-cancel.txt'
    repaired = threading.Event()
    stream_closed = threading.Event()
    modifying = threading.Event()
    edited = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            last = body.get('messages', [{}])[-1]
            content = last.get('content', '')
            compaction = args.auto_compact and last.get('role') == 'user' and isinstance(content, str) and content.startswith(('You MUST summarize', 'Update the existing checkpoint', 'The previous response did not fill'))
            if body.get('tools') and not compaction:
                requests.append(body)
            n = len(requests) if body.get('tools') and not compaction else 0
            if n and args.fault == 'authentication' and not repaired.is_set():
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"Invalid test credential","type":"authentication_error"}}')
                return
            if n and args.fault in ('network-once', 'network-down') and not repaired.is_set() and (n == 1 or args.fault == 'network-down'):
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"Temporary test outage","type":"server_error"}}')
                return
            if n == 0:
                delta = {'content': 'ACP test'}
                if args.auto_compact:
                    delta = {'content': '## Objective\nComplete verification.\n\n## Requirements\nPreserve saved files.\n\n## Decisions\nUse small writes.\n\n## Work State\n### Completed\nSaved recovered.txt as BEFORE_COMPACTION.\n### Active\nFinal report.\n### Blocked\nNone.\n\n## Next Move\nReport ACP_FINAL_OK.\n\n## Relevant Files\nrecovered.txt\n\n## Important Context\nDo not repeat completed writes.'}
            elif args.fresh_session and n == 1:
                delta = {'tool_calls':[{'index':0,'id':'read_existing','type':'function','function':{'name':'read','arguments':json.dumps({'path':str(root/'existing.txt')})}}]}
            elif args.fresh_session and n == 2:
                delta = {'tool_calls':[{'index':0,'id':'edit_existing','type':'function','function':{'name':'edit','arguments':json.dumps({'path':str(root/'existing.txt'),'oldString':'BEFORE_HISTORY_FREE','newString':'AFTER_HISTORY_FREE'})}}]}
            elif args.fresh_session:
                delta = {'content':'ACP_FINAL_OK'}
            elif args.fault and n == 1:
                if args.fault == 'tool-error':
                    arguments = json.dumps({'content': 'missing path'})
                    name = 'write'
                elif args.fault == 'invalid-json':
                    arguments = '{"path":"must-not-exist.txt","content":"broken'
                    name = 'write'
                elif args.fault in ('uac', 'powershell-error', 'interactive', 'long-command'):
                    commands = {'uac': 'Start-Process pwsh -Verb RunAs',
                                'powershell-error': "Write-Error 'EXPECTED_NATIVE_PS_FAILURE'",
                                'interactive': "Read-Host 'Do not prompt an agent'",
                                'long-command': '# long payload\n' * 5000 + "Write-Output LONG_COMMAND_OK"}
                    arguments = json.dumps({'command': commands[args.fault], 'background': False, 'timeout': 15000})
                    name = 'shell'
                else:
                    command = f"Start-Sleep -Seconds 5\nSet-Content -LiteralPath '{marker}' -Value BAD"
                    arguments = json.dumps({'command': command, 'timeout': 200, 'background': False})
                    name = 'shell'
                delta = {'tool_calls': [{'index': 0, 'id': 'fault_probe', 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}
            elif args.fault and n == 2 and args.fault not in ('network-down', 'authentication'):
                delta = {'tool_calls': [{'index': 0, 'id': 'corrected_write', 'type': 'function', 'function': {'name': 'write', 'arguments': json.dumps({'path': str(root / 'recovered.txt'), 'content': 'FAULT_RECOVERED'})}}]}
            elif args.fault:
                delta = {'content': 'ACP_FINAL_OK'}
            elif args.auto_compact and modifying.is_set() and not edited.is_set():
                edited.set()
                delta = {'tool_calls': [{'index': 0, 'id': 'after_compaction_edit', 'type': 'function', 'function': {'name': 'edit', 'arguments': json.dumps({'path': str(root / 'recovered.txt'), 'oldString': 'BEFORE_COMPACTION', 'newString': 'AFTER_COMPACTION_EDIT'})}}]}
            elif args.auto_compact and n == 1:
                delta = {'tool_calls': [{'index': 0, 'id': 'before_compaction', 'type': 'function', 'function': {'name': 'write', 'arguments': json.dumps({'path': str(root / 'recovered.txt'), 'content': 'BEFORE_COMPACTION'})}}]}
            elif args.auto_compact:
                delta = {'content': 'ACP_FINAL_OK'}
            elif n == 1 and args.disconnect:
                command = f"Set-Content -LiteralPath '{started}' -Value $PID\nStart-Sleep -Seconds 15\nSet-Content -LiteralPath '{after_cancel}' -Value BAD"
                delta = {'tool_calls': [{'index': 0, 'id': 'disconnect_shell', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': command, 'background': False, 'timeout': 25000})}}]}
            elif n == 1 and args.subagent:
                delta = {'tool_calls': [{'index': 0, 'id': 'spawn_child', 'type': 'function', 'function': {'name': 'subagent', 'arguments': json.dumps({'agent': 'explore', 'description': 'ACP child regression', 'prompt': 'Return ACP_CHILD_DONE.', 'background': True})}}]}
            elif n == 2 and args.subagent and args.cancel:
                command = f"Set-Content -LiteralPath '{started}' -Value started\nStart-Sleep -Seconds 15\nSet-Content -LiteralPath '{after_cancel}' -Value BAD"
                delta = {'tool_calls': [{'index': 0, 'id': 'cancel_child_shell', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': command, 'background': False, 'timeout': 25000})}}]}
            elif args.subagent:
                delta = {'content': 'ACP_CHILD_DONE' if n == 2 else 'ACP_FINAL_OK'}
            elif n == 1 and (args.late_resume or args.cancel):
                calls = [{'index': 0, 'id': 'schedule_late', 'type': 'function', 'function': {'name': 'test_late_wake', 'arguments': json.dumps({'signal': str(signal), 'fired': str(fired)})}}]
                if args.cancel:
                    command = f"Set-Content -LiteralPath '{started}' -Value started\nStart-Sleep -Seconds 15\nSet-Content -LiteralPath '{after_cancel}' -Value BAD"
                    calls.append({'index': 1, 'id': 'cancel_shell', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': command, 'background': False, 'timeout': 25000})}})
                delta = {'tool_calls': calls}
            elif args.late_resume or args.cancel:
                delta = {'content': 'ACP_FINAL_OK'}
            elif n == 1 and args.output_recovery:
                delta = {'tool_calls': [{'index': 0, 'id': 'call_truncated', 'type': 'function', 'function': {'name': 'write', 'arguments': '{"path":"must-not-exist.txt","content":"unfinished'}}]}
            elif n == 1:
                command = "Set-Content -LiteralPath '" + str(marker) + "' -Value BAD"
                delta = {'tool_calls': [{'index': 0, 'id': 'call_background', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': command, 'background': True})}}]}
            elif n == 2 and args.output_recovery:
                delta = {'tool_calls': [{'index': 0, 'id': 'call_small_write', 'type': 'function', 'function': {'name': 'write', 'arguments': json.dumps({'path': str(root / 'recovered.txt'), 'content': 'RECOVERED_SMALL_WRITE'})}}]}
            elif n == 2:
                delta = {'tool_calls': [{'index': 0, 'id': 'call_foreground', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': "Write-Output ACP_FOREGROUND_OK", 'background': False, 'timeout': 10000})}}]}
            else:
                delta = {'content': 'ACP_FINAL_OK'}
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            if args.cancel_stream and n == 1:
                started.write_text('stream started')
                try:
                    for index in range(300):
                        function = {'name':'write','arguments':'{"path":"must-not-exist.txt","content":"'} if index==0 else {'arguments':'x'}
                        change={'tool_calls':[{'index':0,'id':'streaming_write','type':'function','function':function}]}
                        packet={'choices':[{'index':0,'delta':change,'finish_reason':None}]}
                        self.wfile.write(('data: '+json.dumps(packet)+'\n\n').encode());self.wfile.flush()
                        time.sleep(.05)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                    stream_closed.set()
                return
            finish_reason = 'length' if n == 1 and args.output_recovery else ('tool_calls' if n in (1, 2) else 'stop')
            if args.late_resume or args.cancel:
                finish_reason = 'tool_calls' if n == 1 else 'stop'
            if args.subagent:
                finish_reason = 'tool_calls' if n == 1 or (n == 2 and args.cancel) else 'stop'
            if args.fault or args.auto_compact:
                finish_reason = 'tool_calls' if 'tool_calls' in delta else 'stop'
            for change, finish in [(dict(role='assistant', **delta), None), ({}, finish_reason)]:
                packet = {'id': 'mock', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'test-model', 'choices': [{'index': 0, 'delta': change, 'finish_reason': finish}]}
                if args.auto_compact and finish:
                    packet['usage'] = {'prompt_tokens': args.context - 500 if n == 1 else 100, 'completion_tokens': 64, 'total_tokens': args.context - 436 if n == 1 else 164}
                self.wfile.write(('data: ' + json.dumps(packet) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = root / 'config'
    config.mkdir()
    settings = {
        'update': 'disable', 'model': 'test/test-model',
        'plugins': [{'package':str(plugin), 'options':{'bootstrapPath':str(plugin.parents[2] / 'tools/opencode/powershell-bootstrap.ps1')}}],
        'permissions': [{'action': '*', 'resource': '*', 'effect': 'allow'}],
        'providers': {'test': {'name': 'Test', 'package': 'aisdk:@ai-sdk/openai-compatible',
          'settings': {'apiKey': 'test-key', 'baseURL': f'http://127.0.0.1:{server.server_port}/v1'},
          'models': {'test-model': {'name': 'Test', 'capabilities': {'tools': True, 'input': ['text'], 'output': ['text']}, 'limit': {'context': 100000, 'output': 10000}}}}}
    }
    if args.output_recovery or args.fault == 'invalid-json':
        recovery = plugin.parent / 'output-recovery'
        settings['plugins'].append({'package': str(recovery), 'options': {'providerID': 'test'}})
    # Exercise the same immutable packaging path used by local/remote installers.
    from opencode_runtime_assets import prepare_runtime_assets
    settings['plugins'] = []
    names = ('acp', 'output') if args.output_recovery or args.fault == 'invalid-json' else ('acp',)
    for dest, content in prepare_runtime_assets(settings, config, names=names).items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    if 'output' in names:
        settings['plugins'][-1] = {'package': settings['plugins'][-1], 'options': {'providerID':'test'}}
    if args.auto_compact:
        settings['providers']['test']['models']['test-model']['limit'] = {'context': args.context, 'output': 1000}
        settings['compaction'] = {'auto': True, 'buffer': args.context // 4, 'keep': {'tokens': min(12000, args.context // 8)}}
    if args.late_resume or (args.cancel and not args.subagent):
        fixture = root / 'fixture-plugin'
        fixture.mkdir()
        (fixture / 'package.json').write_text('{"type":"module","main":"index.js"}')
        (fixture / 'index.js').write_text('''import {existsSync,writeFileSync} from 'node:fs';
export default {id:'test.late-wake', async setup(ctx){
 const timers=new Set();
 await ctx.tool.transform(e=>e.add({name:'test_late_wake',description:'Test fixture',input:{type:'object',properties:{signal:{type:'string'},fired:{type:'string'}},required:['signal','fired']},options:{codemode:false},
 execute:async(input,call)=>{
  let count=0; const timer=setInterval(async()=>{
   if(!existsSync(input.signal)&&++count<200)return;
   clearInterval(timer);timers.delete(timer);
   if(!existsSync(input.signal))return;
   await ctx.session.synthetic({sessionID:call.sessionID,text:'Late automatic completion. Continue working now.',description:'test late completion'});
   writeFileSync(input.fired,'fired');
  },50);timers.add(timer);return {content:'Scheduled test completion'};
 }}));
 return ()=>{for(const timer of timers)clearInterval(timer);};
}};''', encoding='utf-8')
        settings['plugins'].append(str(fixture))
    (config / 'opencode.json').write_text(json.dumps(settings), encoding='utf-8')
    (root / 'models.json').write_text('{}')
    env = dict(os.environ)
    for key in ('OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_CLI_CONFIG_CONTENT'):
        env.pop(key, None)
    env.update({'HOME': str(root), 'USERPROFILE': str(root), 'OPENCODE_CONFIG_DIR': str(config), 'OPENCODE_DB': str(root / 'opencode.db'), 'OPENCODE_TEST_HOME': str(root), 'OPENCODE_DISABLE_AUTOUPDATE': 'true', 'OPENCODE_DISABLE_FILEWATCHER': 'true', 'OPENCODE_DISABLE_MODELS_FETCH': 'true', 'OPENCODE_MODELS_PATH': str(root / 'models.json'), 'OPENCODE_ACP_FOREGROUND_GUARD': '1', 'OPENCODE_ACP_TURN_GUARD': '1', 'OPENCODE_ACP_TERMINAL_GUARD': '1'})
    for key, folder in [('XDG_CONFIG_HOME', 'xdg-config'), ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
        env[key] = str(root / folder)
    stderr = (root / 'stderr.log').open('w', encoding='utf-8')
    child = subprocess.Popen([args.binary, 'acp'], cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8')
    inbox = queue.Queue()
    def read():
        for line in child.stdout:
            try:
                message = json.loads(line)
                events.append(message)
                inbox.put(message)
            except ValueError:
                events.append({'invalid': line})
    threading.Thread(target=read, daemon=True).start()
    def send(value):
        child.stdin.write(json.dumps(value) + '\n')
        child.stdin.flush()
    def rpc(number, method, params):
        rpc_started = time.monotonic()
        send({'jsonrpc': '2.0', 'id': number, 'method': method, 'params': params})
        end = time.monotonic() + 120
        while time.monotonic() < end:
            message = inbox.get(timeout=max(0.1, end - time.monotonic()))
            if message.get('method') == 'session/request_permission':
                options = message['params']['options']
                option = next(o for o in options if o['kind'] in ('allow_once', 'allow_always'))
                send({'jsonrpc': '2.0', 'id': message['id'], 'result': {'outcome': {'outcome': 'selected', 'optionId': option['optionId']}}})
            if message.get('id') == number and 'method' not in message:
                rpc_timings.append({'method':method,'elapsed_ms':round((time.monotonic()-rpc_started)*1000,2),'error':'error' in message})
                if 'error' in message:
                    raise RuntimeError(message['error'])
                return message['result']
        raise TimeoutError(method)
    def wait_for(check, label, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if check():
                return
            time.sleep(0.05)
        raise AssertionError(label)
    def late_blocked():
        with sqlite3.connect(f'file:{(root / "opencode.db").as_posix()}?mode=ro', uri=True) as db:
            row = db.execute("select data from session_message where type='idle' order by time_created desc limit 1").fetchone()
            return row is not None and json.loads(row[0]).get('outcome') == 'failed'
    try:
        rpc(1, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {}, 'clientInfo': {'name': 'strata-regression', 'version': '1'}})
        session = rpc(2, 'session/new', {'cwd': str(root), 'mcpServers': []})
        prompt = {'sessionId': session['sessionId'], 'prompt': [{'type': 'text', 'text': 'Run the verification and report its result.'}]}
        if args.fresh_session:
            result=rpc(3,'session/prompt',{'sessionId':session['sessionId'],'prompt':[{'type':'text','text':'Read existing.txt and change BEFORE_HISTORY_FREE to AFTER_HISTORY_FREE. Preserve unrelated files. This is a new session without previous chat.'}]})
            assert result['stopReason']=='end_turn',result
            assert (root/'existing.txt').read_text()=='AFTER_HISTORY_FREE'
            assert (root/'unrelated.txt').read_text()=='KEEP_EXISTING_WORK'
            assert 'BEFORE_HISTORY_FREE' in json.dumps([m for m in requests[1]['messages'] if m['role']=='tool']), 'Existing file was not read before editing'
            assert len(requests)==3,'Unexpected extra model loop'
            print('PASS: new DB/session reads existing file and applies targeted edit without chat history; unrelated work preserved (scripted model)')
            return
        if args.cancel or args.disconnect:
            outcome = queue.Queue()
            def pending_prompt():
                try:
                    outcome.put(rpc(3, 'session/prompt', prompt))
                except Exception as error:
                    outcome.put(error)
            worker = threading.Thread(target=pending_prompt, daemon=True)
            worker.start()
            wait_for(started.exists, 'Foreground shell did not start')
            if args.disconnect:
                shell_pid = int(started.read_text(encoding='utf-8-sig').strip())
                child.stdin.close()
                child.wait(timeout=15)
                assert not after_cancel.exists(), 'Shell kept running after ACP EOF'
                import ctypes
                api = ctypes.windll.kernel32
                api.OpenProcess.restype = ctypes.c_void_p
                handle = api.OpenProcess(0x1000, False, shell_pid)
                if handle:
                    code = ctypes.c_ulong()
                    api.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
                    api.CloseHandle(ctypes.c_void_p(handle))
                    assert code.value != 259, 'Owned shell process still alive after ACP EOF'
                print('PASS: ACP stdin EOF exits process and stops owned shell before remaining work')
                return
            cancel_started=time.monotonic()
            send({'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': session['sessionId']}})
            result = outcome.get(timeout=20)
            if isinstance(result, Exception):
                raise result
            assert result['stopReason'] == 'cancelled', result
            assert not after_cancel.exists(), 'Cancelled shell still executed remaining work'
            if args.cancel_stream:
                wait_for(stream_closed.is_set,'Mock model connection did not close after cancellation',timeout=5)
                assert not marker.exists(),'Partial streaming write was executed'
                elapsed=time.monotonic()-cancel_started
                count=len(requests)
                assert rpc(4,'session/prompt',prompt)['stopReason']=='end_turn'
                assert len(requests)==count+1,'Cancel caused extra model requests'
                print(f'PASS: generation cancelled in {elapsed:.3f}s; mock connection closed; partial tool not executed; follow-up succeeds (not GPU cancellation proof)')
                return
        else:
            try:
                result = rpc(3, 'session/prompt', prompt)
            except RuntimeError:
                if args.fault not in ('network-down', 'authentication'):
                    raise
                expected_attempts = 1 if args.fault == 'authentication' else 4
                assert len(requests) == expected_attempts, f'Expected {expected_attempts} attempts, got {len(requests)}'
                repaired.set()
                assert rpc(4, 'session/prompt', prompt)['stopReason'] == 'end_turn'
                assert len(requests) == expected_attempts + 1, 'Server recovery did not accept the new user request'
                print(f'PASS: {args.fault} stops after {expected_attempts} attempts; repaired server accepts same-session follow-up')
                return
        if args.fault:
            assert result['stopReason'] == 'end_turn', result
            assert (root / 'recovered.txt').read_text() == 'FAULT_RECOVERED'
            assert not marker.exists(), 'Timed-out or malformed work still changed the target'
            if args.fault not in ('network-once', 'network-down'):
                tool_results = [m for m in requests[1]['messages'] if m['role'] == 'tool']
                assert tool_results, 'Fault was not reported to the model'
                if args.fault in ('uac', 'powershell-error', 'interactive', 'long-command'):
                    expected = {'uac': 'BLOCKED_UAC', 'powershell-error': 'EXPECTED_NATIVE_PS_FAILURE', 'interactive': 'NonInteractive', 'long-command': 'LONG_COMMAND_OK'}[args.fault]
                    assert expected in json.dumps(tool_results), 'Native PowerShell dispatch did not return expected evidence'
            count = len(requests)
            assert rpc(4, 'session/prompt', prompt)['stopReason'] == 'end_turn'
            assert len(requests) == count + 1
            print(f'PASS: {args.fault} recovered inside same ACP request; corrected file saved; follow-up succeeds')
            return
        if args.auto_compact:
            assert result['stopReason'] == 'end_turn', result
            assert (root / 'recovered.txt').read_text() == 'BEFORE_COMPACTION'
            compact_events = [e for e in events if 'compaction' in json.dumps(e.get('params', {}).get('update', {}).get('_meta', {}))]
            assert compact_events, 'No automatic compaction was observed'
            assert any('auto' in json.dumps(e) and 'completed' in json.dumps(e) for e in compact_events), 'Automatic compaction did not finish'
            modifying.set()
            assert rpc(4, 'session/prompt', {'sessionId': session['sessionId'], 'prompt': [{'type': 'text', 'text': 'Change recovered.txt from BEFORE_COMPACTION to AFTER_COMPACTION_EDIT.'}]})['stopReason'] == 'end_turn'
            assert (root / 'recovered.txt').read_text() == 'AFTER_COMPACTION_EDIT', 'Post-compaction edit was not saved'
            for file, digest in unrelated.items():
                assert file.exists() and hashlib.sha256(file.read_bytes()).hexdigest() == digest, f'Unrelated file changed: {file}'
            if unrelated:
                print(f'PASS: {len(unrelated)} unrelated nested files preserved across compaction and follow-up edit (scripted model, not navigation quality)')
            print(f'PASS: simulated {args.context}-token budget triggers auto-compaction; saved work and subsequent edit complete')
            return
        if args.subagent:
            if not args.cancel:
                assert result['stopReason'] == 'end_turn', result
                assert len(requests) == 3, 'Parent did not await child'
                assert 'ACP_CHILD_DONE' in json.dumps(requests[2]), 'Child result did not reach parent'
                with sqlite3.connect(f'file:{(root / "opencode.db").as_posix()}?mode=ro', uri=True) as db:
                    assert db.execute('select count(*) from session_pending').fetchone()[0] == 0
                    assert db.execute('select count(*) from session_inbox').fetchone()[0] == 0
            count = len(requests)
            assert rpc(4, 'session/prompt', prompt)['stopReason'] == 'end_turn'
            assert len(requests) == count + 1, 'Follow-up must make exactly one request'
            print('PASS: subagent background request awaited inside parent ACP turn; ' + ('child shell cancelled and follow-up succeeds' if args.cancel else 'child result delivered before parent completion; follow-up succeeds'))
            return
        if args.late_resume or args.cancel:
            count = len(requests)
            signal.write_text('go')
            wait_for(fired.exists, 'Synthetic completion was not submitted')
            wait_for(late_blocked, 'Late automatic resume was not blocked')
            assert len(requests) == count, 'Hidden inference reached model after ACP completion/cancellation'
            assert not after_cancel.exists(), 'Cancelled shell resumed'
            assert rpc(4, 'session/prompt', prompt)['stopReason'] == 'end_turn'
            assert len(requests) == count + 1, 'New user follow-up did not run exactly once'
            print('PASS: late auto-resume blocked before model HTTP; same-session follow-up succeeds; ' + ('cancelled shell stopped' if args.cancel else 'completed request stays finished'))
            return
        serialized = json.dumps(events)
        assert not marker.exists(), 'Blocked command executed'
        assert len(requests) == 3, f'Unexpected request count {len(requests)}'
        expected = 'OUTPUT_TRUNCATED' if args.output_recovery else 'ACP_BACKGROUND_BLOCKED'
        assert expected in json.dumps(requests[1]), 'Model did not receive recovery result'
        if args.output_recovery:
            assert (root / 'recovered.txt').read_text() == 'RECOVERED_SMALL_WRITE', 'Recovery file was not saved'
        else:
            assert 'ACP_FOREGROUND_OK' in json.dumps(requests[2]), 'Foreground shell failed'
        assert 'ACP_FINAL_OK' in serialized, 'Final update not delivered'
        assert result['stopReason'] == 'end_turn', result
        action = 'small write saved' if args.output_recovery else 'foreground output received'
        print(f'PASS: {expected}; incomplete command not executed; {action}; final update delivered before end_turn')
        if args.reconnect:
            count = len(requests)
            child.stdin.close()
            child.wait(timeout=15)
            child = subprocess.Popen([args.binary, 'acp'], cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8')
            inbox = queue.Queue()
            threading.Thread(target=read, daemon=True).start()
            rpc(10, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {}, 'clientInfo': {'name': 'strata-regression', 'version': '1'}})
            rpc(11, 'session/load', {'sessionId': session['sessionId'], 'cwd': str(root), 'mcpServers': []})
            assert len(requests) == count, 'Loading history must not replay completed work'
            assert rpc(12, 'session/prompt', prompt)['stopReason'] == 'end_turn'
            assert len(requests) == count + 1
            print('PASS: restarted ACP loads session without replaying work; new user follow-up succeeds')
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
        server.shutdown()
        stderr.close()
        (root / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        (root / 'requests.json').write_text(json.dumps(requests, indent=2), encoding='utf-8')
        (root / 'rpc-timings.json').write_text(json.dumps(rpc_timings, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
