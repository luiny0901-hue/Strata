"""Read-only catalog and refused-input checks against the installed MCP proxy."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--coordinates', action='store_true', help='Also inspect one visible window screenshot without clicking')
    options = parser.parse_args()
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
        assert not any(tool['name'] == 'launch_app' for tool in tools), 'Focus-stealing launch tool still advertised'
        refused_launch = rpc(90, 'tools/call', {'name':'launch_app','arguments':{'path':'THIS_MUST_NOT_LAUNCH.exe'}})
        assert refused_launch.get('isError') and refused_launch['structuredContent']['code'] == 'permission_denied'
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
        if options.coordinates:
            def meta(value):
                if value.get('structuredContent'):
                    return value['structuredContent']
                for content in value.get('content', []):
                    if content.get('type') == 'text':
                        try:
                            return json.loads(content['text'])
                        except ValueError:
                            pass
                return {}
            refused = rpc(20, 'tools/call', {'name': 'click', 'arguments': {'pid': 2147483647, 'window_id': 2147483647, 'x': 10, 'y': 10}})
            assert refused.get('isError') and refused['structuredContent']['code'] == 'fresh_screenshot_required', refused
            windows = meta(rpc(21, 'tools/call', {'name': 'list_windows', 'arguments': {}})).get('windows', [])
            candidates = [w for w in windows if w.get('pid') and w.get('is_on_screen') and not w.get('minimized') and w['bounds']['width'] > 200 and w['bounds']['height'] > 200]
            assert candidates, 'No visible window for read-only verification'
            window = next((w for w in candidates if w.get('app_name', '').lower() in ('windowsterminal.exe', 'explorer.exe')), candidates[0])
            snapshot = rpc(22, 'tools/call', {'name': 'get_window_state', 'arguments': {'pid': window['pid'], 'window_id': window['window_id'], 'include_accessibility_tree': False}})
            notes = [v.get('text', '') for v in snapshot.get('content', []) if v.get('type') == 'text']
            assert any('CUA_COORDINATES:' in t for t in notes), {'keys': list(snapshot), 'meta_keys': list(meta(snapshot)), 'notes': notes}
            bounds = meta(snapshot).get('window_bounds')
            assert bounds and all(isinstance(bounds.get(k), (int, float)) for k in ('x', 'y', 'width', 'height')), 'Snapshot lacks reliable overlay conversion bounds'
            # Out-of-range input must be refused by the proxy; never dispatch a click.
            refused = rpc(23, 'tools/call', {'name': 'click', 'arguments': {'pid': window['pid'], 'window_id': window['window_id'], 'x': 1e9, 'y': 1e9}})
            assert refused.get('isError') and refused['structuredContent']['code'] == 'fresh_screenshot_required', refused
            print('PASS: actual PNG dimensions annotated; missing capture and out-of-bounds clicks refused; no native click dispatched')
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == '__main__':
    main()
