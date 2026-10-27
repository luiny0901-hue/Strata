"""Windows lifecycle adapter for one checkpointed Claude Desktop restart.

Uses Windows Restart Manager and the installed native Claude Code --resume.
Restores the existing conversation by its link or configured background CUA.
No physical pointer/keyboard injection or debug port.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG_RELATIVE = Path('.config/strata/server-control/desktop-restart.json')
MAX_JSON = 1024 * 1024
MAX_TRANSCRIPT_TAIL = 2 * 1024 * 1024
# An owned session whose transcript stopped moving is interrupted or waiting on a
# human, not running a model request; it must not block a handoff forever.
STALE_OTHER_SESSION_SECONDS = 15 * 60


class HandoffBlockedError(ValueError):
    """Timeout cause with a fixed public category, never private text."""

    def __init__(self, code, message):
        self.handoff_code = code
        super().__init__(message)


def canonical_session(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Use the exact lowercase Claude Code session UUID')
    return value


def regular(path, *, root=None, limit=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Expected one regular file without links')
    resolved = path.resolve()
    if root is not None and not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError('File is outside its declared project/profile')
    if limit is not None and path.stat().st_size > limit:
        raise ValueError('File exceeds the bounded maintenance size')
    return resolved


def read_json(path, *, root=None):
    value = json.loads(regular(path, root=root, limit=MAX_JSON).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def tail_events(path, *, offset=None):
    path = regular(path)
    size = path.stat().st_size
    start = max(0, size - MAX_TRANSCRIPT_TAIL, offset or 0)
    with path.open('rb') as stream:
        stream.seek(start)
        raw = stream.read(MAX_TRANSCRIPT_TAIL + 1)
    if len(raw) > MAX_TRANSCRIPT_TAIL:
        raise ValueError('Transcript observation exceeded its bounded window')
    lines = raw.splitlines()
    if start and (offset is None or start != offset):
        lines = lines[1:]
    result = []
    for line in lines:
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if isinstance(row, dict) and not row.get('isSidechain'):
            result.append(row)
    return result


def dialog_state(events):
    """Do not mistake a thinking fragment or a pending tool result for end_turn."""
    state = 'unknown'
    for row in events:
        kind = row.get('type')
        message = row.get('message') or {}
        blocks = message.get('content')
        if kind in ('user', 'api-request', 'attachment'):
            state = 'busy'
        elif kind == 'assistant':
            text = isinstance(blocks, list) and any(
                isinstance(block, dict) and block.get('type') == 'text'
                and isinstance(block.get('text'), str) and block['text'].strip() for block in blocks)
            state = ('idle' if message.get('stop_reason') == 'end_turn' and text else 'busy')
    return state


def accepted_then_finished(events, operation_id):
    def accepted_payload(value):
        if isinstance(value, str):
            try:
                return accepted_payload(json.loads(value))
            except (ValueError, TypeError):
                return False
        if isinstance(value, list):
            return any(accepted_payload(item) for item in value)
        if not isinstance(value, dict) or value.get('is_error') is True or value.get('isError') is True:
            return False
        if value.get('operation_id') == operation_id:
            return value.get('accepted') is True and value.get('state') in ('queued', 'waiting_for_handoff')
        if value.get('type') == 'text':
            return accepted_payload(value.get('text'))
        return accepted_payload(value.get('structuredContent')) or accepted_payload(value.get('content'))

    accepted = False
    state = 'unknown'
    for row in events:
        message = row.get('message') or {}
        blocks = message.get('content')
        if row.get('type') == 'user' and isinstance(blocks, list):
            for block in blocks:
                if (isinstance(block, dict) and block.get('type') == 'tool_result'
                        and block.get('is_error') is not True and accepted_payload(block.get('content'))):
                    accepted = True
        next_state = dialog_state([row])
        if next_state != 'unknown':
            state = next_state
    return accepted and state == 'idle'


class StreamSummary:
    """Drain native CLI output without retaining code, prompts or tool payloads."""
    def __init__(self):
        self.pending = bytearray()
        self.bytes = 0
        self.events = 0
        self.result = None
        self.oversized = False
        self.discarding = False

    def write(self, data):
        self.bytes += len(data)
        if self.discarding:
            newline = data.find(b'\n')
            if newline == -1:
                return
            data = data[newline + 1:]
            self.discarding = False
        self.pending.extend(data)
        while b'\n' in self.pending:
            raw, _, rest = self.pending.partition(b'\n')
            self.pending = bytearray(rest)
            if len(raw) > MAX_TRANSCRIPT_TAIL:
                self.oversized = True
            else:
                self._line(raw)
        if len(self.pending) > MAX_TRANSCRIPT_TAIL:
            self.pending.clear()
            self.oversized = True
            self.discarding = True

    def _line(self, raw):
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeError):
            return
        if not isinstance(row, dict):
            return
        self.events += 1
        if row.get('type') == 'result':
            self.result = {key: row[key] for key in ('subtype', 'is_error', 'session_id', 'num_turns')
                           if key in row}

    def finish(self):
        if self.pending and not self.discarding:
            self._line(self.pending)
            self.pending.clear()


class WindowsDesktopSystem:
    """Existing app identity only; normal Restart Manager shutdown, never force."""
    def __init__(self):
        if os.name != 'nt':
            raise ValueError('Automatic Desktop restart is currently Windows-only')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
        self.advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        self.kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self.sid = self.identity(os.getpid())['sid']

    @staticmethod
    def powershell(script, timeout=12):
        prefix = '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $ErrorActionPreference="Stop"; '
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', prefix + script],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or len(result.stdout) > 4 * MAX_JSON:
            raise ValueError('Cannot inspect the installed Desktop owner')
        return json.loads(result.stdout.decode('utf-8-sig'))

    def discover(self, family=None):
        value = self.powershell("@(Get-AppxPackage -Name 'Claude' | Select-Object PackageFamilyName,InstallLocation,Version) | ConvertTo-Json -Compress")
        rows = value if isinstance(value, list) else [value]
        rows = [row for row in rows if isinstance(row, dict) and
                (family is None or row.get('PackageFamilyName') == family)]
        if len(rows) != 1:
            raise ValueError('Expected exactly one installed Claude Desktop package')
        row = rows[0]
        import xml.etree.ElementTree as ET
        install = Path(row['InstallLocation']).resolve()
        manifest = ET.parse(regular(install/'AppxManifest.xml', root=install)).getroot()
        apps = [node for node in manifest.iter() if node.tag.rsplit('}', 1)[-1] == 'Application'
                and node.attrib.get('Id') == 'Claude']
        if len(apps) != 1:
            raise ValueError('Claude package application identity is ambiguous')
        exe = regular(install/apps[0].attrib['Executable'], root=install)
        return {'family': row['PackageFamilyName'], 'version': row['Version'], 'exe': str(exe),
                'app_id': row['PackageFamilyName'] + '!Claude'}

    def snapshot(self):
        rows = self.powershell('@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Compress', timeout=15)
        return {int(row['ProcessId']): {'pid': int(row['ProcessId']), 'parent': int(row['ParentProcessId']),
                'exe': row.get('ExecutablePath') or '', 'command': row.get('CommandLine') or ''}
                for row in rows if isinstance(row, dict)}

    def identity(self, pid):
        handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            raise ValueError('Process is absent or not queryable')
        token = wintypes.HANDLE()
        try:
            path = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(path))
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) or not self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
                raise ValueError('Cannot verify process path/start time')
            if not self.advapi.OpenProcessToken(handle, 8, ctypes.byref(token)):
                raise ValueError('Cannot verify process user')
            needed = wintypes.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
            buffer = ctypes.create_string_buffer(needed.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
                raise ValueError('Cannot read process user')
            sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            sid_text = wintypes.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_text)):
                raise ValueError('Cannot identify process user')
            try:
                sid = sid_text.value
            finally:
                self.kernel.LocalFree(sid_text)
            return {'pid': int(pid), 'started': (created.dwHighDateTime << 32) | created.dwLowDateTime,
                    'exe': str(Path(path.value).resolve()), 'sid': sid}
        finally:
            if token:
                self.kernel.CloseHandle(token)
            self.kernel.CloseHandle(handle)

    def matches(self, identity):
        try:
            return self.identity(identity['pid']) == identity
        except (ValueError, KeyError, TypeError, OSError):
            return False

    def main(self, package, snapshot=None):
        rows = (snapshot or self.snapshot()).values()
        matches = []
        for row in rows:
            if row['exe'] and Path(row['exe']).resolve() == Path(package['exe']).resolve() and '--type=' not in row['command']:
                identity = self.identity(row['pid'])
                if identity['sid'] == self.sid:
                    matches.append(identity)
        if len(matches) != 1:
            raise ValueError('Expected one running Desktop main process owned by this user')
        return matches[0]

    def quit(self, identity):
        if not self.matches(identity) or identity['sid'] != self.sid:
            raise ValueError('Desktop identity changed; no shutdown was requested')
        rm = ctypes.WinDLL('rstrtmgr', use_last_error=True)
        class UniqueProcess(ctypes.Structure):
            _fields_ = [('pid', wintypes.DWORD), ('started', wintypes.FILETIME)]
        rm.RmStartSession.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR]
        rm.RmRegisterResources.argtypes = [wintypes.DWORD, wintypes.UINT, ctypes.c_void_p, wintypes.UINT,
                                         ctypes.POINTER(UniqueProcess), wintypes.UINT, ctypes.c_void_p]
        rm.RmShutdown.argtypes = [wintypes.DWORD, wintypes.ULONG, ctypes.c_void_p]
        rm.RmEndSession.argtypes = [wintypes.DWORD]
        session = wintypes.DWORD(); key = ctypes.create_unicode_buffer(33)
        code = rm.RmStartSession(ctypes.byref(session), 0, key)
        if code:
            raise ValueError(f'Restart Manager session failed ({code})')
        try:
            process = UniqueProcess(identity['pid'], wintypes.FILETIME(identity['started'] & 0xffffffff,
                                                                     identity['started'] >> 32))
            code = rm.RmRegisterResources(session, 0, None, 1, ctypes.byref(process), 0, None)
            if code:
                raise ValueError(f'Restart Manager registration failed ({code})')
            # No RmForceShutdown; only the exact PID/start-time pair is registered.
            code = rm.RmShutdown(session, 0, None)
            if code:
                raise ValueError(f'Desktop declined normal shutdown ({code}); no force was used')
        finally:
            rm.RmEndSession(session)
        deadline = time.monotonic() + 30
        while self.matches(identity) and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.matches(identity):
            raise ValueError('Desktop did not exit after normal shutdown')

    @staticmethod
    def launch(desktop_session_id):
        if not re.fullmatch(r'local_[0-9a-f-]{36}', desktop_session_id):
            raise ValueError('Invalid exact Desktop session ID')
        uri = 'claude://code/continue?session=' + quote(desktop_session_id, safe='')
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
        shell.ShellExecuteW.restype = ctypes.c_void_p
        if int(shell.ShellExecuteW(None, 'open', uri, None, None, 1) or 0) <= 32:
            raise ValueError('Desktop existing-session link could not be opened')


class DesktopRuntime:
    def __init__(self, config, *, home=None, system=None):
        self.config = dict(config)
        self.home = Path(home or Path.home()).resolve()
        self.user_data = Path(config['user_data_dir']).resolve()
        if config.get('version') != 1 or config.get('enabled') is not True:
            raise ValueError('Desktop restart is not explicitly enabled')
        if not self.user_data.is_dir() or self.user_data.is_symlink():
            raise ValueError('Configured Desktop user data is absent or linked')
        self.system = system or WindowsDesktopSystem()

    def _sessions(self):
        root = self.user_data/'claude-code-sessions'
        files = list(root.glob('*/*/local_*.json'))
        if len(files) > 2000:
            raise ValueError('Desktop session inventory exceeds the bounded limit')
        for path in files:
            try:
                row = read_json(path, root=root)
            except (ValueError, OSError):
                continue
            yield path, row

    def _session(self, cli_id):
        matches = [(path, row) for path, row in self._sessions() if row.get('cliSessionId') == cli_id]
        if len(matches) != 1:
            raise ValueError('The exact CLI session is not uniquely owned by this Desktop profile')
        return matches[0]

    def _transcript(self, cli_id):
        files = list((self.home/'.claude/projects').glob(f'*/{cli_id}.jsonl'))
        if len(files) != 1:
            raise ValueError('The exact session transcript is absent or ambiguous')
        return regular(files[0], root=self.home/'.claude/projects')

    def _model(self, row):
        # Consume the existing common setup's route receipt instead of choosing
        # another provider or copying Desktop's transient credential environment.
        owner = read_json(self.home/'.claude/strata-opencodex.json')
        settings = read_json(self.home/'.claude/settings.json')
        base, route = owner.get('base_url'), owner.get('model')
        if (settings.get('env', {}).get('ANTHROPIC_BASE_URL') != base
                or settings.get('model') != route):
            raise ValueError('Common Claude route changed; refresh its existing setup before recovery')
        if base != 'http://127.0.0.1:10100' or not isinstance(route, str) or not route.startswith('strata/'):
            raise ValueError('Recovery requires the configured local OpenCodex/Strata route')
        library = self.user_data/'configLibrary'
        selected = read_json(library/'_meta.json')['appliedId']
        selected = str(uuid.UUID(selected))
        profile = read_json(library/(selected + '.json'), root=library)
        defaults = [model.get('name') for model in profile.get('inferenceModels', [])
                    if isinstance(model, dict) and model.get('isFamilyDefault') is True]
        if (profile.get('inferenceProvider') != 'gateway' or profile.get('inferenceGatewayBaseUrl') != base
                or row.get('model') not in (route, *defaults)):
            raise ValueError('Session model is not this profile\'s current Strata default')
        return route

    @staticmethod
    def _session_identity(row):
        return {key: row.get(key) for key in ('sessionId', 'cliSessionId', 'cwd', 'model', 'effort', 'permissionMode')}

    def _binding_path(self, identity):
        return self.home/CONFIG_RELATIVE.parent/'desktop-sessions'/f'{identity["pid"]}-{identity["started"]}.json'

    def record_session_start(self, event, caller_pid):
        """Bind the native hook's UUID to the live process birth, never recency.

        Desktop initializes fresh sessions through its SDK input stream; their
        command lines legitimately contain neither --session-id nor --resume.
        """
        cli_id = canonical_session(event.get('session_id'))
        project = Path(event['cwd']).resolve()
        snapshot = self.system.snapshot()
        desktop = self.system.main(self.system.discover(self.config.get('package_family')), snapshot)
        current = int(caller_pid); native = None
        for _ in range(24):
            row = snapshot.get(current)
            if not row:
                break
            if row['exe'] and Path(row['exe']).resolve().is_relative_to(self.user_data/'claude-code'):
                native = self.system.identity(current)
                if native['sid'] != self.system.sid:
                    raise ValueError('Native hook belongs to another user')
            if current == desktop['pid']:
                if native is None:
                    break
                path = self._binding_path(native)
                if path.parent.is_symlink():
                    raise ValueError('Session binding directory must not be linked')
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if path.exists():
                    regular(path, root=path.parent, limit=65536)
                try:
                    from .strata_server_supervisor import publish
                except ImportError:
                    from strata_server_supervisor import publish
                publish(path, {'version': 1, 'cli_session_id': cli_id, 'project': str(project),
                               'native_identity': native, 'desktop_identity': desktop})
                return
            current = row['parent']
        raise ValueError('SessionStart hook is not owned by the running Desktop')

    def _process_session(self, process):
        identity = self.system.identity(process['pid'])
        if identity['sid'] != self.system.sid:
            raise ValueError('Native session belongs to another user')
        match = re.search(r'(?:--session-id|--resume|-r)(?:=|\s+)"?([0-9a-f-]{36})(?:"|\s|$)', process['command'])
        if match:
            return canonical_session(match[1])
        record = read_json(self._binding_path(identity), root=self.home/CONFIG_RELATIVE.parent/'desktop-sessions')
        if (record.get('version') != 1 or record.get('native_identity') != identity
                or not self.system.matches(record.get('desktop_identity', {}))):
            raise ValueError('Native session binding is stale or belongs to another process')
        return canonical_session(record.get('cli_session_id'))

    def current_session_id(self, caller_pid):
        """Identify the caller's native session, never the most recent session."""
        snapshot = self.system.snapshot(); current = int(caller_pid)
        for _ in range(24):
            row = snapshot.get(current)
            if not row:
                break
            if row['exe'] and Path(row['exe']).resolve().is_relative_to(self.user_data/'claude-code'):
                return self._process_session(row)
            current = row['parent']
        raise ValueError('Current caller is not a session-identifiable native Claude Code process')

    def prepare_binding(self, session_id, checkpoint_path, caller_pid):
        cli_id = canonical_session(session_id)
        session_file, row = self._session(cli_id)
        if row.get('isArchived') or not re.fullmatch(r'local_[0-9a-f-]{36}', row.get('sessionId', '')):
            raise ValueError('An active local Desktop session is required')
        project = Path(row['cwd']).resolve()
        if not project.is_dir():
            raise ValueError('Session working directory is absent')
        checkpoint = regular(checkpoint_path, root=project, limit=65536)
        if not checkpoint.read_text(encoding='utf-8').strip():
            raise ValueError('Save completed/remaining work in a nonempty UTF-8 checkpoint first')
        transcript = self._transcript(cli_id)
        version = row.get('cliBinaryPin', {}).get('version')
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Session has no installed native CLI version pin')
        binaries = list((self.user_data/'claude-code'/version).glob('*/claude.exe'))
        if len(binaries) != 1:
            raise ValueError('Pinned Desktop native Claude Code executable is absent or ambiguous')
        cli = regular(binaries[0], root=self.user_data/'claude-code')
        permission = row.get('permissionMode')
        if permission not in ('default', 'acceptEdits', 'plan', 'auto', 'bypassPermissions', 'dontAsk'):
            raise ValueError('Session permission mode cannot be preserved')
        effort = row.get('effort')
        if effort is not None and effort not in ('low', 'medium', 'high'):
            raise ValueError('Session reasoning effort cannot be preserved')
        flags = subprocess.run([str(cli), '--help'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=10,
                               **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        if flags.returncode or len(flags.stdout) > 256 * 1024 or any(
                flag not in flags.stdout for flag in (b'--resume', b'--print', b'--output-format', b'--permission-mode', b'--effort')):
            raise ValueError('Installed native CLI lacks the required resume/print options')
        package = self.system.discover(self.config.get('package_family'))
        snapshot = self.system.snapshot()
        desktop = self.system.main(package, snapshot)
        caller = self.system.identity(int(caller_pid))
        if caller['sid'] != self.system.sid:
            raise ValueError('Maintenance caller belongs to another user')
        current = int(caller_pid); requester = None; desktop_ancestor = False
        for _ in range(24):
            process = snapshot.get(current)
            if not process:
                break
            if process['exe'] and Path(process['exe']).resolve() == cli:
                if self._process_session(process) != cli_id:
                    raise ValueError('Calling native CLI does not identify the requested session')
                requester = self.system.identity(current)
                if requester['sid'] != self.system.sid:
                    raise ValueError('Requesting native Code process belongs to another user')
            if current == desktop['pid']:
                desktop_ancestor = requester is not None
                break
            current = process['parent']
        if requester is None or not desktop_ancestor:
            raise ValueError('Restart must be requested from the native Code session being resumed')
        return {'cli_session_id': cli_id, 'desktop_session_id': row['sessionId'], 'project': str(project),
                'session_file': str(session_file), 'session_identity': self._session_identity(row),
                'transcript': str(transcript), 'transcript_offset': transcript.stat().st_size,
                'checkpoint_path': str(checkpoint), 'checkpoint_sha256': digest(checkpoint),
                'cli_path': str(cli), 'cli_sha256': digest(cli), 'model': self._model(row),
                'effort': effort, 'permission_mode': permission, 'desktop_identity': desktop,
                'requester_identity': requester, 'package': package,
                'focused_before': row.get('lastFocusedAt', 0)}

    def _unchanged(self, binding):
        if digest(regular(binding['checkpoint_path'], root=binding['project'], limit=65536)) != binding['checkpoint_sha256']:
            raise ValueError('Checkpoint changed after submission; no restart was performed')
        row = read_json(binding['session_file'], root=self.user_data/'claude-code-sessions')
        if self._session_identity(row) != binding['session_identity'] or row.get('isArchived'):
            raise ValueError('Session identity/settings changed after submission')
        if not self.system.matches(binding['desktop_identity']):
            raise ValueError('Original Desktop process identity changed')

    def _other_sessions_idle(self, binding):
        snapshot = self.system.snapshot(); main_pid = binding['desktop_identity']['pid']
        cli_root = self.user_data/'claude-code'
        for process in snapshot.values():
            if not process['exe'] or not Path(process['exe']).resolve().is_relative_to(cli_root):
                continue
            if process['pid'] == binding['requester_identity']['pid']:
                continue
            ancestor = process['parent']; owned = False
            for _ in range(24):
                if ancestor == main_pid:
                    owned = True; break
                parent = snapshot.get(ancestor)
                if not parent:
                    break
                ancestor = parent['parent']
            if not owned:
                continue
            try:
                cli_id = self._process_session(process)
                transcript = self._transcript(cli_id)
                state = dialog_state(tail_events(transcript))
                age = time.time() - transcript.stat().st_mtime
            except (OSError, ValueError, KeyError):
                return False
            if state != 'idle' and age <= STALE_OTHER_SESSION_SECONDS:
                return False
        return True

    def wait_for_handoff(self, binding, cancel_event, deadline):
        stable = None
        blocked = 'original_turn_unfinished'
        while time.monotonic() < deadline:
            if cancel_event.is_set():
                return
            self._unchanged(binding)
            finished = accepted_then_finished(tail_events(binding['transcript'], offset=binding['transcript_offset']),
                                             binding['operation_id'])
            if finished:
                if self._other_sessions_idle(binding):
                    stable = stable or time.monotonic()
                    if time.monotonic() - stable >= 1:
                        return
                    blocked = 'other_sessions_busy'
                else:
                    stable = None
                    blocked = 'other_sessions_busy'
            else:
                stable = None
                blocked = 'original_turn_unfinished'
            cancel_event.wait(0.25)
        raise HandoffBlockedError(blocked, 'Original turn did not finish or another Desktop session is busy; no shutdown was requested')

    def quit(self, binding):
        self._unchanged(binding)
        if not self._other_sessions_idle(binding):
            raise ValueError('Another Desktop session became busy; no shutdown was requested')
        self.system.quit(binding['desktop_identity'])
        deadline = time.monotonic() + 30
        while self.system.matches(binding['requester_identity']) and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.system.matches(binding['requester_identity']):
            raise ValueError('Original native session still owns its transcript; no duplicate resume was started')

    def continue_session(self, binding, operation_id, nonce, cancel_event, deadline):
        def check_active():
            if cancel_event.is_set():
                raise ValueError('Recovery cancelled; saved files are preserved')
            if time.monotonic() >= deadline:
                raise ValueError('Recovery deadline reached; inspect the saved checkpoint before resuming')
            row = read_json(binding['session_file'], root=self.user_data/'claude-code-sessions')
            if row.get('lastFocusedAt', 0) != binding.get('focused_before', 0):
                raise ValueError('Desktop session was reopened during recovery; stop the owned continuation')
        check_active()
        if digest(regular(binding['cli_path'], root=self.user_data/'claude-code')) != binding['cli_sha256']:
            raise ValueError('Pinned native CLI changed; no resume was started')
        if digest(regular(binding['checkpoint_path'], root=binding['project'], limit=65536)) != binding['checkpoint_sha256']:
            raise ValueError('Checkpoint changed before recovery; no resume was started')
        if self.system.matches(binding['requester_identity']):
            raise ValueError('Original session process is still running')
        prompt = (
            '이 요청은 사용자가 승인한 현재 유지보수 작업의 Desktop 재시작 후 재개입니다. '
            f'체크포인트 파일 {binding["checkpoint_path"]}을 먼저 읽고 실제 파일·diff와 완료/미완료를 대조하세요. '
            '그 뒤 strata-maintenance의 acknowledge_desktop_restart 도구에 '
            f'operation_id={operation_id}, nonce={nonce}, session_id={binding["cli_session_id"]}를 전달하세요. '
            '수락되지 않거나 취소 상태면 추가 작업을 멈추세요. 수락되면 체크포인트의 미완료 작업과 필요한 검증만 '
            '이 요청 안에서 이어가고 이미 완료한 작업을 반복하지 마세요. 같은 Desktop 재시작을 다시 제출하지 마세요. '
            '복구 중에는 동일한 네이티브 Claude Code CLI를 한 번 사용하며, 종료되면 외부 소유자가 원래 Desktop 대화를 엽니다. '
            '필수 결과를 확인하고 한국어로 보고하세요. 이 실행이 종료됐다는 사실만으로 전체 프로젝트 완료를 단정하지 마세요.')
        command = [binding['cli_path'], '--resume', binding['cli_session_id'], '--print',
                   '--output-format', 'stream-json', '--verbose', '--model', binding['model'],
                   '--permission-mode', binding['permission_mode']]
        if binding.get('effort'):
            command += ['--effort', binding['effort']]
        command.append(prompt)
        env = dict(os.environ)
        for name in list(env):
            if name.startswith(('ANTHROPIC_', 'OPENCODE_', 'STRATA_CUA_TASK_', 'CLAUDE_DESKTOP_', 'CLAUDE_CODE_HOST_')) or name in (
                    'CLAUDECODE', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_ENTRYPOINT',
                    'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_RETRY_WATCHDOG', 'STRATA_SUPERVISOR_CHILD',
                    'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY'):
                env.pop(name, None)
        try:
            from .strata_server_supervisor import OwnedProcess
        except ImportError:
            from strata_server_supervisor import OwnedProcess
        summary = StreamSummary()
        process = OwnedProcess(command, summary, cwd=binding['project'], environment=env)
        try:
            check_active()
            process.start()
            while process.alive():
                if cancel_event.wait(0.2):
                    raise ValueError('Recovery cancelled; saved files are preserved')
                if time.monotonic() >= deadline:
                    raise ValueError('Recovery deadline reached; inspect the saved checkpoint before resuming')
            code = process.child.returncode
            check_active()
        finally:
            process.stop(grace_seconds=2)
        summary.finish()
        check_active()
        result = summary.result or {}
        if result.get('session_id') != binding['cli_session_id']:
            raise ValueError('Recovery did not confirm the original session identity')
        return {'exit_code': code, 'subtype': result.get('subtype'), 'is_error': result.get('is_error', True),
                'num_turns': result.get('num_turns'), 'output_bytes': summary.bytes,
                'event_count': summary.events, 'oversized_output_line': summary.oversized}

    def reopen(self, binding):
        self.system.launch(binding['desktop_session_id'])
        started = time.monotonic(); deadline = started + 45
        cua_attempted = False
        while time.monotonic() < deadline:
            try:
                package = self.system.discover(self.config.get('package_family'))
                current = self.system.main(package)
                row = read_json(binding['session_file'], root=self.user_data/'claude-code-sessions')
                if (current != binding['desktop_identity'] and row.get('sessionId') == binding['desktop_session_id']
                        and row.get('lastFocusedAt', 0) > binding.get('focused_before', 0)):
                    return
                if (not cua_attempted and time.monotonic()-started >= 8
                        and self.config.get('ui_restore') == 'configured_cua_background'):
                    cua_attempted = True
                    self._restore_cua(binding, current, deadline)
            except (ValueError, OSError):
                pass
            time.sleep(0.5)
        raise ValueError('Desktop launch was requested once; exact session focus was not confirmed')

    def _restore_cua(self, binding, desktop, deadline):
        client = Path(self.config['client_root']).resolve()
        helper = regular(client/'tools/claude_desktop_restore.py', root=client)
        python = regular(self.config['client_python'])
        command = [str(python), '-X', 'utf8', str(helper), '--desktop-pid', str(desktop['pid']),
                   '--desktop-started', str(desktop['started']), '--session-file', binding['session_file'],
                   '--native-session', binding['cli_session_id']]
        class Output:
            def __init__(self):
                self.data = bytearray()
            def write(self, chunk):
                if len(self.data)+len(chunk) > 65536:
                    raise ValueError('Background restoration output exceeded its metadata bound')
                self.data.extend(chunk)
        try:
            from .strata_server_supervisor import OwnedProcess
        except ImportError:
            from strata_server_supervisor import OwnedProcess
        output = Output(); process = OwnedProcess(command, output, cwd=client, environment=dict(os.environ))
        try:
            process.start()
            while process.alive():
                if process.log_error or time.monotonic() >= deadline:
                    raise ValueError('Background restoration deadline/output failed; no replay')
                time.sleep(.1)
            code = process.child.returncode
        finally:
            process.stop(grace_seconds=2)
        if code != 0 or json.loads(output.data).get('state') != 'focused':
            raise ValueError('Background conversation restoration was not confirmed')


def record_session_start(event, home=None):
    """Optional SessionStart hook receipt; no effect on ordinary/disabled setups."""
    home = Path(home or Path.home())
    config = home/CONFIG_RELATIVE
    if os.name != 'nt' or not config.is_file() or event.get('hook_event_name') != 'SessionStart':
        return
    try:
        DesktopRuntime(read_json(config), home=home).record_session_start(event, os.getpid())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        # A registry failure must not break the existing language/project hook.
        # The restart preflight will fail closed instead of guessing a session.
        return


def configure(home=None):
    home = Path(home or Path.home())
    system = WindowsDesktopSystem(); package = system.discover()
    override = os.environ.get('CLAUDE_3P_CONFIG_LIBRARY')
    user_data = (Path(override).resolve().parent if override else Path(os.environ['LOCALAPPDATA'])/'Claude-3p')
    if not (user_data/'configLibrary/_meta.json').is_file() or not (user_data/'claude-code-sessions').is_dir():
        raise ValueError('Configure and use the local Desktop Code gateway profile first')
    try:
        from .strata_server_supervisor import private_directory
        from .claude_opencodex_client import publish_files
        from .configure_strata_managed_launchers import enable_managed_launchers
    except ImportError:
        from strata_server_supervisor import private_directory
        from claude_opencodex_client import publish_files
        from configure_strata_managed_launchers import enable_managed_launchers
    target = home/CONFIG_RELATIVE
    private_directory(target.parent)
    before = target.read_bytes() if target.exists() else None
    if before is not None:
        previous = json.loads(before)
        if not isinstance(previous, dict) or previous.get('owner') != 'strata-desktop-restart':
            raise ValueError('Existing Desktop restart configuration is not owned by this setup')
    config = {'version': 1, 'owner': 'strata-desktop-restart', 'enabled': True, 'package_family': package['family'],
              'user_data_dir': str(user_data.resolve()), 'ui_restore': 'configured_cua_background',
              'client_root': str(ROOT), 'client_python': str(Path(sys.executable).resolve())}
    backup, changed = publish_files({target: json.dumps(config, ensure_ascii=False, indent=2)+'\n'},
                                    home/'.claude', {target: before})
    enable_managed_launchers(home)
    return {'config': str(target), 'enabled': True, 'desktop_version': package['version'],
            'changed': changed, 'backup': str(backup) if backup else None,
            'activation': 'The existing Strata supervisor loads this opt-in configuration on its next start.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('configure',))
    args = parser.parse_args()
    try:
        print(json.dumps(configure(), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f'Desktop restart configuration: {exc}\n')
