"""Read-only catalog and refused-input checks against the installed MCP proxy."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading


def main():
    config = json.loads((Path.home() / '.config/opencode/opencode.json').read_text(encoding='utf-8-sig'))
    mcp = config['mcp']
    server = mcp.get('cua-driver') or mcp['servers']['cua-driver']
    env = dict(os.environ, **server['environment'])
    child = subprocess.Popen(server['command'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env)
    inbox = queue.Queue()
    errors = []
    def read():
        for line in child.stdout:
            try:
                inbox.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=lambda: errors.extend(child.stderr), daemon=True).start()
    def rpc(number, method, params):
        child.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': number, 'method': method, 'params': params}) + '\n')
        child.stdin.flush()
        while True:
            result = inbox.get(timeout=25)
            if result.get('id') == number:
                assert 'error' not in result, result
                return result['result']
    try:
        init = rpc(1, 'initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'background-policy-verifier', 'version': '1'}})
        assert 'BACKGROUND_ONLY_UNSUPPORTED' in init['instructions']
        tools = rpc(2, 'tools/list', {})['tools']
        inputs = ['click', 'double_click', 'right_click', 'drag', 'scroll', 'type_text', 'press_key', 'hotkey', 'set_value']
        for tool in tools:
            if tool['name'] in inputs:
                assert tool['inputSchema']['properties']['delivery_mode']['enum'] == ['background']
        # Intentionally invalid window IDs: these calls must be rejected before native dispatch.
        for number, name in enumerate(inputs, 3):
            result = rpc(number, 'tools/call', {'name': name, 'arguments': {'target': {'kind': 'window', 'pid': 2147483647, 'window_id': 2147483647}, 'delivery_mode': 'foreground'}})
            assert result.get('isError') is True, result
            assert result['structuredContent']['code'] == 'permission_denied', result
        print('PASS: installed catalog is background-only; all 9 foreground input tools refused before dispatch')
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == '__main__':
    main()
