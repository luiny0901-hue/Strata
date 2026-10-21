"""Opt-in installed OpenCode ACP regression; isolated DB and local mock model."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    requests = []
    events = []
    marker = root / 'must-not-exist.txt'
    plugin = Path(__file__).resolve().parents[1] / 'examples/opencode/acp-foreground-guard'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if body.get('tools'):
                requests.append(body)
            n = len(requests) if body.get('tools') else 0
            if n == 0:
                delta = {'content': 'ACP test'}
            elif n == 1:
                command = "Set-Content -LiteralPath '" + str(marker) + "' -Value BAD"
                delta = {'tool_calls': [{'index': 0, 'id': 'call_background', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': command, 'background': True})}}]}
            elif n == 2:
                delta = {'tool_calls': [{'index': 0, 'id': 'call_foreground', 'type': 'function', 'function': {'name': 'shell', 'arguments': json.dumps({'command': "Write-Output ACP_FOREGROUND_OK", 'background': False, 'timeout': 10000})}}]}
            else:
                delta = {'content': 'ACP_FINAL_OK'}
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for change, finish in [(dict(role='assistant', **delta), None), ({}, 'tool_calls' if n in (1, 2) else 'stop')]:
                packet = {'id': 'mock', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'test-model', 'choices': [{'index': 0, 'delta': change, 'finish_reason': finish}]}
                self.wfile.write(('data: ' + json.dumps(packet) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = root / 'config'
    config.mkdir()
    settings = {
        'update': 'disable', 'model': 'test/test-model',
        'plugins': [str(plugin)],
        'permissions': [{'action': '*', 'resource': '*', 'effect': 'allow'}],
        'providers': {'test': {'name': 'Test', 'package': 'aisdk:@ai-sdk/openai-compatible',
          'settings': {'apiKey': 'test-key', 'baseURL': f'http://127.0.0.1:{server.server_port}/v1'},
          'models': {'test-model': {'name': 'Test', 'capabilities': {'tools': True, 'input': ['text'], 'output': ['text']}, 'limit': {'context': 100000, 'output': 10000}}}}}
    }
    (config / 'opencode.json').write_text(json.dumps(settings), encoding='utf-8')
    (root / 'models.json').write_text('{}')
    env = dict(os.environ)
    for key in ('OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_CLI_CONFIG_CONTENT'):
        env.pop(key, None)
    env.update({'HOME': str(root), 'USERPROFILE': str(root), 'OPENCODE_CONFIG_DIR': str(config), 'OPENCODE_DB': str(root / 'opencode.db'), 'OPENCODE_TEST_HOME': str(root), 'OPENCODE_DISABLE_AUTOUPDATE': 'true', 'OPENCODE_DISABLE_FILEWATCHER': 'true', 'OPENCODE_DISABLE_MODELS_FETCH': 'true', 'OPENCODE_MODELS_PATH': str(root / 'models.json'), 'OPENCODE_ACP_FOREGROUND_GUARD': '1'})
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
        send({'jsonrpc': '2.0', 'id': number, 'method': method, 'params': params})
        end = time.monotonic() + 120
        while time.monotonic() < end:
            message = inbox.get(timeout=max(0.1, end - time.monotonic()))
            if message.get('method') == 'session/request_permission':
                options = message['params']['options']
                option = next(o for o in options if o['kind'] in ('allow_once', 'allow_always'))
                send({'jsonrpc': '2.0', 'id': message['id'], 'result': {'outcome': {'outcome': 'selected', 'optionId': option['optionId']}}})
            if message.get('id') == number and 'method' not in message:
                if 'error' in message:
                    raise RuntimeError(message['error'])
                return message['result']
        raise TimeoutError(method)
    try:
        rpc(1, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {}, 'clientInfo': {'name': 'strata-regression', 'version': '1'}})
        session = rpc(2, 'session/new', {'cwd': str(root), 'mcpServers': []})
        result = rpc(3, 'session/prompt', {'sessionId': session['sessionId'], 'prompt': [{'type': 'text', 'text': 'Run the verification and report its result.'}]})
        serialized = json.dumps(events)
        assert not marker.exists(), 'Blocked command executed'
        assert len(requests) == 3, f'Unexpected request count {len(requests)}'
        assert 'ACP_BACKGROUND_BLOCKED' in json.dumps(requests[1]), 'Model did not receive rejection'
        assert 'ACP_FOREGROUND_OK' in json.dumps(requests[2]), 'Foreground shell failed'
        assert 'ACP_FINAL_OK' in serialized, 'Final update not delivered'
        assert result['stopReason'] == 'end_turn', result
        print('PASS: blocked before execution; foreground output and final update delivered before end_turn')
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


if __name__ == '__main__':
    main()
