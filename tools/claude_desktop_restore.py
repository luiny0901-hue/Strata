"""Restore one verified Desktop conversation through configured background CUA.

The 3p shell can deliberately disable OS entry links. This uses its normal
sidebar through the existing policy-bound CUA server; no foreground escalation,
physical pointer, keyboard, guessed coordinates or repeated click is available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import threading
import time

if __package__:
    from .claude_desktop_runtime import CONFIG_RELATIVE, WindowsDesktopSystem, canonical_session, read_json
    from .claude_mcp.lazy_dispatcher import configured_servers, search_catalog
else:
    from claude_desktop_runtime import CONFIG_RELATIVE, WindowsDesktopSystem, canonical_session, read_json
    from claude_mcp.lazy_dispatcher import configured_servers, search_catalog


def exact_conversation_button(state, *, pid, window_id, title):
    elements = state.get('elements', [])
    # The driver omits layout-only nodes and reports elements_complete=false
    # even after a finished walk. Require its explicit drain/count evidence.
    drained = (state.get('nodes_pending') == 0 and state.get('returned_element_count') == len(elements)
               and state.get('total_element_count') == len(elements)
               and type(state.get('nodes_visited')) is int and state['nodes_visited'] >= len(elements))
    if (state.get('pid') != pid or state.get('window_id') != window_id
            or state.get('truncated') is not False
            or not (state.get('elements_complete') is True or drained)):
        raise ValueError('Incomplete or mismatched Desktop observation')
    matches = [row for row in elements if row.get('role') == 'Button'
               and row.get('label') == title and row.get('enabled') is True
               and 'invoke' in row.get('actions', [])]
    if len(matches) != 1:
        raise ValueError('Desktop conversation is absent or its title is ambiguous')
    token = matches[0].get('element_token')
    if not isinstance(token, str) or not re.fullmatch(r's[0-9a-f]{8}:[0-9]+', token):
        raise ValueError('No current scoped accessibility token')
    if not token.startswith(str(state.get('snapshot_id')) + ':'):
        raise ValueError('Stale accessibility token')
    return token


def restore(server, system, desktop, session_file, native_id, *, deadline, clock=time.monotonic):
    """One observed semantic click, then exact on-disk session focus proof."""
    native_id = canonical_session(native_id)
    row = read_json(session_file)
    title = row.get('title')
    if row.get('cliSessionId') != native_id or not isinstance(title, str) or not title.strip():
        raise ValueError('Exact conversation identity/title is unavailable')
    before = row.get('lastFocusedAt', 0)
    cancel = threading.Event()
    timer = threading.Timer(max(.1, deadline-clock()), cancel.set); timer.daemon = True; timer.start()
    try:
        for name in ('list_windows', 'get_window_state', 'click'):
            if not any(tool['name'] == name for tool in search_catalog(server, name, 1, cancel_event=cancel)):
                raise ValueError('Required configured background CUA tool is unavailable')
        windows = server.call('list_windows', {'pid': desktop['pid']}, cancel_event=cancel)
        if windows.get('isError'):
            raise ValueError('Window enumeration failed')
        windows = [w for w in windows.get('structuredContent', {}).get('windows', [])
                   if w.get('pid') == desktop['pid'] and w.get('is_on_screen') is True and not w.get('minimized')]
        if len(windows) != 1:
            raise ValueError('Expected one visible verified Desktop window')
        window_id = windows[0]['window_id']
        state = server.call('get_window_state', {'pid': desktop['pid'], 'window_id': window_id,
            'include_screenshot': False, 'tree_format': 'elements', 'max_elements': 500,
            'max_depth': 25, 'verbose': True, 'timeout_ms': 2000}, cancel_event=cancel)
        if state.get('isError'):
            raise ValueError('Desktop observation failed')
        token = exact_conversation_button(state.get('structuredContent', {}), pid=desktop['pid'],
                                          window_id=window_id, title=title)
        if not system.matches(desktop) or cancel.is_set():
            raise ValueError('Desktop owner/deadline changed before input')
        latest = read_json(session_file)
        if any(latest.get(key) != row.get(key) for key in ('sessionId', 'cliSessionId', 'title', 'lastFocusedAt')):
            raise ValueError('Conversation changed before input')
        action = server.call('click', {'element_token': token, 'delivery_mode': 'background'}, cancel_event=cancel)
        data = action.get('structuredContent', {})
        if (action.get('isError') or data.get('effect') in ('refused', 'suspected_noop')
                or data.get('route') not in ('accessibility', 'synthetic_events', 'system_api')
                or (data.get('delivery') or {}).get('mode') not in ('background', 'not_applicable')):
            raise ValueError('Background navigation failed; do not repeat input')
        while clock() < deadline:
            latest = read_json(session_file)
            if (system.matches(desktop) and latest.get('sessionId') == row['sessionId']
                    and latest.get('cliSessionId') == native_id and latest.get('lastFocusedAt', 0) > before):
                return {'state': 'focused', 'method': 'cua_background', 'click_count': 1}
            if cancel.wait(.2):
                break
        raise ValueError('Exact conversation focus was not confirmed after one click')
    finally:
        timer.cancel()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-pid', type=int, required=True)
    parser.add_argument('--desktop-started', type=int, required=True)
    parser.add_argument('--session-file', type=Path, required=True)
    parser.add_argument('--native-session', required=True)
    args = parser.parse_args()
    home = Path.home(); config = read_json(home/CONFIG_RELATIVE)
    if config.get('ui_restore') != 'configured_cua_background':
        raise ValueError('Background CUA restoration is not enabled')
    system = WindowsDesktopSystem(); desktop = system.main(system.discover(config.get('package_family')))
    if desktop['pid'] != args.desktop_pid or desktop['started'] != args.desktop_started:
        raise ValueError('Desktop process identity changed')
    session = read_json(args.session_file, root=Path(config['user_data_dir'])/'claude-code-sessions')
    if session.get('cliSessionId') != canonical_session(args.native_session):
        raise ValueError('Native session identity changed')
    servers = configured_servers(home/'.claude/strata-mcp.json')
    try:
        result = restore(servers['cua-driver'], system, desktop, args.session_file, args.native_session,
                         deadline=time.monotonic()+20)
        print(json.dumps(result), flush=True)
    finally:
        for child in servers.values():
            child.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'state': 'needs_attention', 'error_code': 'background_restore_unconfirmed'}), flush=True)
        raise SystemExit(2)
