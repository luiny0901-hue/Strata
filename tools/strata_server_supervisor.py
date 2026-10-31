"""Opt-in external owner for one Strata launcher and bounded restart transactions.

The model cannot change the command, endpoint or credentials. The tool waits for
this separate process; no model callback or replay of a completed turn is used.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def publish(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Supervisor private directory must not be a symlink')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        if path.stat().st_uid != os.getuid():
            raise ValueError('Supervisor private directory must belong to the current user')
        os.chmod(path,0o700)
        return
    # This changes only the dedicated control/state directory, not the API-key directory.
    script = ("$ErrorActionPreference='Stop'; $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User; "
              "$acl=[Security.AccessControl.DirectorySecurity]::new(); $acl.SetAccessRuleProtection($true,$false); "
              "$acl.SetOwner($sid); $flags=[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'; "
              "$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl',$flags,'None','Allow')); "
              "[IO.Directory]::SetAccessControl($env:STRATA_CONTROL_DIRECTORY,$acl)")
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                   env={**os.environ,'STRATA_CONTROL_DIRECTORY':str(path.resolve())},
                   check=True,timeout=15,capture_output=True)


@contextlib.contextmanager
def owner_lock(directory):
    private_directory(directory)
    with (directory / 'owner.lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class BoundedLog:
    """Bound disk use without stopping stdout consumption or buffering whole lines."""
    def __init__(self, path, max_bytes=8*1024*1024, backups=3):
        if max_bytes < 1 or backups < 1:
            raise ValueError('Positive log size and backup count are required')
        self.path, self.max_bytes, self.backups = path, max_bytes, backups
        self.lock = threading.Lock()
        # Apply the same retain-newest policy to oversized logs from older versions.
        for existing in [path,*[path.with_name(path.name+f'.{n}') for n in range(1,backups+1)]]:
            if existing.exists() and existing.stat().st_size>max_bytes:
                with existing.open('r+b') as stream:
                    stream.seek(-max_bytes,os.SEEK_END)
                    tail=stream.read(max_bytes)
                    stream.seek(0);stream.write(tail);stream.truncate()
        self.stream = path.open('ab',buffering=0)

    def rotate(self):
        self.stream.close()
        oldest=self.path.with_name(self.path.name+f'.{self.backups}')
        oldest.unlink(missing_ok=True)
        for number in range(self.backups-1,0,-1):
            previous=self.path.with_name(self.path.name+f'.{number}')
            if previous.exists():
                os.replace(previous,self.path.with_name(self.path.name+f'.{number+1}'))
        os.replace(self.path,self.path.with_name(self.path.name+'.1'))
        self.stream=self.path.open('ab',buffering=0)

    def write(self, data):
        with self.lock:
            offset=0
            while offset<len(data):
                space=self.max_bytes-self.stream.tell()
                if space<=0:
                    self.rotate()
                    space=self.max_bytes
                end=min(len(data),offset+space)
                written=self.stream.write(data[offset:end])
                if not written:
                    raise OSError('Server log write made no progress')
                offset+=written

    def close(self):
        with self.lock:
            self.stream.close()


class OwnedProcess:
    """Never adopt a PID from disk or search by executable/port to kill it."""
    def __init__(self, command, log, *, console_log=False, cwd=None, environment=None):
        self.command, self.log, self.child, self.job = command, log, None, None
        self.console_log = console_log
        self.output_thread, self.log_error = None, None
        self.cwd, self.environment = cwd, environment

    def start(self):
        env = (dict(self.environment) if self.environment is not None else
               dict(os.environ, STRATA_SUPERVISOR_CHILD='1', PYTHONUNBUFFERED='1'))
        options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.PIPE,
                   'stderr': subprocess.STDOUT, 'env': env}
        if self.cwd is not None:
            options['cwd'] = self.cwd
        command = self.command
        if os.name == 'nt':
            # A Job Object owns descendants even if the BAT's cmd.exe exits first.
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            self.kernel, self.job = kernel, kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise OSError('Cannot create process ownership job')
            class BasicLimit(ctypes.Structure):
                _fields_ = [('per_process', ctypes.c_longlong), ('per_job', ctypes.c_longlong),
                            ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t),
                            ('max_working', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                            ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
            class ExtendedLimit(ctypes.Structure):
                _fields_ = [('basic', BasicLimit), ('io', IO), ('process_memory', ctypes.c_size_t),
                            ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
            limits = ExtendedLimit()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                kernel.CloseHandle(self.job)
                self.job = None
                raise OSError('Cannot set owned process-tree cleanup policy')
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            if Path(command[0]).suffix.lower() in ('.bat', '.cmd'):
                if len(command) != 1 or any(c in command[0] for c in '"%!\r\n'):
                    raise ValueError('BAT launcher must be one literal path without expansion characters')
                command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{command[0]}""'
            # A waiting bridge prevents the launcher from spawning descendants
            # before it has joined our Job Object. No guessed/adopted child PIDs.
            bridge = ('import subprocess,sys; ready=sys.stdin.buffer.read(1); '
                      'cmd=sys.argv[2] if sys.argv[1]=="raw" else sys.argv[2:]; '
                      'sys.exit(subprocess.call(cmd) if ready==b"1" else 125)')
            command = [sys.executable, '-c', bridge,
                       'raw' if isinstance(command, str) else 'argv',
                       *([command] if isinstance(command, str) else command)]
            options['stdin'] = subprocess.PIPE
        else:
            options['start_new_session'] = True
        self.child = subprocess.Popen(command, **options)
        if os.name == 'nt':
            if not self.kernel.AssignProcessToJobObject(self.job, int(self.child._handle)):
                self.child.kill()
                self.child.wait(timeout=10)
                self.child.stdout.close()
                self.kernel.CloseHandle(self.job)
                self.job = None
                raise OSError('Cannot establish process-tree ownership; server was stopped')
            self.child.stdin.write(b'1')
            self.child.stdin.flush()
            self.child.stdin.close()
        self.log_error = None
        output = self.child.stdout
        def drain():
            try:
                while chunk := output.read1(65536):
                    if self.log_error is None:
                        try:
                            self.log.write(chunk)
                        except (OSError,ValueError) as exc:
                            self.log_error = str(exc)
                            # Keep draining to avoid a full pipe deadlocking the child.
                    if self.console_log:
                        try:
                            sys.stdout.buffer.write(chunk)
                            sys.stdout.buffer.flush()
                        except (OSError, ValueError, AttributeError):
                            # A detached/closed console must not stop log draining.
                            self.console_log = False
            finally:
                output.close()
        self.output_thread = threading.Thread(target=drain,daemon=True)
        self.output_thread.start()

    def alive(self):
        return self.child is not None and self.child.poll() is None

    def stop(self, *, grace_seconds=30):
        if self.child is None:
            return
        try:
            if self.alive():
                try:
                    if os.name == 'nt':
                        self.child.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        os.killpg(self.child.pid, signal.SIGTERM)
                    self.child.wait(timeout=grace_seconds)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if os.name == 'nt' and self.job:
                if not self.kernel.TerminateJobObject(self.job, 1):
                    raise OSError('Owned process-tree termination failed')
                import ctypes
                class Accounting(ctypes.Structure):
                    _fields_ = [('times', ctypes.c_longlong * 4), ('page_faults', ctypes.c_ulong),
                                ('total', ctypes.c_ulong), ('active', ctypes.c_ulong), ('terminated', ctypes.c_ulong)]
                deadline = time.monotonic() + 15
                while True:
                    accounting = Accounting()
                    if not self.kernel.QueryInformationJobObject(self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                        raise OSError('Cannot verify owned process-tree drain')
                    if accounting.active == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Owned process tree did not drain')
                    time.sleep(0.05)
            elif os.name != 'nt':
                try:
                    os.killpg(self.child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.child.wait(timeout=15)
        finally:
            if os.name == 'nt' and self.job:
                self.kernel.CloseHandle(self.job)
                self.job = None
            if self.output_thread:
                self.output_thread.join(timeout=5)
                if self.output_thread.is_alive():
                    raise RuntimeError('Owned output pipe did not drain; replacement not started')


class Supervisor:
    def __init__(self, directory, command, server_url, key_file, model, *, ready_timeout=600, console_log=False,
                 updates=None, client_home=None):
        self.directory, self.server_url = directory, server_url.rstrip('/')
        self.key_file, self.model, self.ready_timeout = key_file, model, ready_timeout
        self.expected_model, self.client_home = model, client_home
        self.log = BoundedLog(directory / 'server.log')
        self.process = OwnedProcess(command, self.log, console_log=console_log)
        self.lock, self.stopping = threading.RLock(), threading.Event()
        self.job = None
        self.worker = None
        self.transaction_active = False
        self.persistence_error = None
        self.updates = updates
        self.update_worker = None
        checkpoint = directory / 'restart.json'
        if checkpoint.exists():
            self.job = json.loads(checkpoint.read_text(encoding='utf-8'))
            if self.job['state'] not in ('ready', 'failed', 'cancelled'):
                self.job.update(state='failed', error='Supervisor interrupted; inspect saved work before requesting a new restart')
                publish(checkpoint, self.job)
                publish(directory / (hashlib.sha256(self.job['operation_id'].encode()).hexdigest()+'.json'), self.job)

    def api(self, route):
        key = self.key_file.read_text(encoding='utf-8').strip()
        req = Request(self.server_url + route, headers={'Authorization': 'Bearer ' + key})
        with urlopen(req, timeout=3) as response:
            raw=response.read(256*1024+1)
        if len(raw)>256*1024:
            raise RuntimeError('Server control response exceeded 256 KiB; readiness is unconfirmed')
        return json.loads(raw)

    def port_open(self):
        url = urlsplit(self.server_url)
        try:
            with socket.create_connection((url.hostname, url.port or 80), timeout=1):
                return True
        except OSError:
            return False

    def wait_ready(self):
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline and not self.stopping.is_set():
            if not self.process.alive():
                raise RuntimeError('Owned server launcher exited; see server.log')
            if self.process.log_error:
                raise RuntimeError('Cannot persist server log: '+self.process.log_error)
            try:
                health, models = self.api('/health'), self.api('/v1/models')
                model = self.expected_model or health.get('model')
                if (health.get('status') == 'ok' and health.get('loaded') is True
                        and isinstance(model, str) and bool(model)
                        and any(m.get('id') == model for m in models.get('data', []))):
                    self.model = model
                    return
            except HTTPError as exc:
                if exc.code in (401,403):
                    raise RuntimeError('Readiness authentication failed; check the configured API key file') from None
            except (OSError, ValueError):
                pass
            self.stopping.wait(0.5)
        raise RuntimeError('Server did not become ready within the deadline')

    def start(self):
        if self.port_open():
            raise RuntimeError('Server port is occupied. No existing server was adopted or stopped.')
        transaction = self.updates.activate(self) if self.updates else None
        try:
            self.process.start()
            self.wait_ready()
            if transaction:
                self.updates.ready(transaction)
        except BaseException as exc:
            self.process.stop()
            if not isinstance(exc, Exception) or not transaction or self.stopping.is_set() or self.port_open():
                raise
            self.updates.restore(transaction, 'Candidate readiness failed; previous fork restored')
            print('Strata update did not become ready; restoring the previous fork.', flush=True)
            self.process.start()
            try:
                self.wait_ready()
            except BaseException:
                self.process.stop()
                raise
        if self.client_home is not None:
            configure_client_context(self, self.client_home)

    def watch_updates(self):
        # Only this owner watches; a release never triggers a live restart.
        while not self.stopping.is_set():
            try:
                result = self.updates.check(stopped=self.stopping.is_set)
                print('Strata stable update: ' + result['status'] +
                      ('; applies on next server start' if result['status'] == 'prepared' else ''), flush=True)
            except (OSError, ValueError):
                print('Strata update check unavailable; current service retained.', flush=True)
            self.stopping.wait(86400)

    def snapshot(self):
        with self.lock:
            # Receipt fields are immutable strings/bools. Serialization here
            # repeatedly copied a 16K checkpoint during polling for no benefit.
            return dict(self.job) if self.job else None

    def save(self, **values):
        with self.lock:
            self.job.update(values)
            publish(self.directory / 'restart.json', self.job)

    def request(self, operation_id, checkpoint):
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 128:
            raise ValueError('operation_id must be a nonempty string of at most 128 characters')
        if not isinstance(checkpoint, str) or not checkpoint.strip() or len(checkpoint) > 16000:
            raise ValueError('Save completed/remaining work and paths in a checkpoint of 1..16000 characters')
        digest = hashlib.sha256(checkpoint.encode()).hexdigest()
        with self.lock:
            if self.persistence_error:
                raise ValueError('Previous receipt could not be persisted; inspect supervisor state before restarting')
            cancelled = self.directory / (hashlib.sha256(operation_id.encode()).hexdigest() + '.cancelled')
            if cancelled.exists():
                raise ValueError('This operation was cancelled; it will not start a restart')
            if self.job and self.job['operation_id'] == operation_id:
                if self.job['checkpoint_hash'] != digest:
                    raise ValueError('operation_id already belongs to a different checkpoint')
                return self.snapshot()
            if self.job and self.job['state'] not in ('ready', 'failed', 'cancelled'):
                raise ValueError('A restart transaction is already active')
            if self.transaction_active:
                raise ValueError('Previous restart receipt is still being committed')
            # Keep every operation receipt, not just the most recent transaction.
            receipt = self.directory / (hashlib.sha256(operation_id.encode()).hexdigest() + '.json')
            if receipt.exists():
                old = json.loads(receipt.read_text(encoding='utf-8'))
                if old['checkpoint_hash'] != digest:
                    raise ValueError('operation_id already belongs to a different checkpoint')
                return old
            self.job = dict(operation_id=operation_id, checkpoint=checkpoint,
                            checkpoint_hash=digest, state='queued', cancelled=False)
            publish(self.directory / 'restart.json', self.job)
            self.transaction_active = True
            self.worker = threading.Thread(target=self.restart, daemon=True)
            try:
                self.worker.start()
            except RuntimeError:
                self.worker=None
                record={**self.job,'state':'failed','error':'Restart worker could not start; server was not stopped'}
                try:
                    publish(receipt,record)
                    publish(self.directory/'restart.json',record)
                except OSError as exc:
                    self.persistence_error=str(exc)
                else:
                    self.transaction_active=False
                self.job=record
                raise ValueError(record['error']) from None
            return self.snapshot()

    def cancel(self, operation_id):
        if not isinstance(operation_id,str) or not 0 < len(operation_id) <= 128:
            raise ValueError('Invalid operation_id')
        with self.lock:
            # /cancel may overtake an uncertain /restart HTTP delivery.
            publish(self.directory / (hashlib.sha256(operation_id.encode()).hexdigest()+'.cancelled'),
                    {'operation_id':operation_id,'cancelled':True})
            if self.job and self.job['operation_id'] == operation_id:
                self.save(cancelled=True)

    def restart(self):
        with self.lock:
            operation_id = self.job['operation_id']
        terminal={'state':'failed','error':'Restart did not settle'}
        try:
            self.save(state='draining')
            deadline = time.monotonic() + 60
            while True:
                if self.stopping.is_set() or self.snapshot()['cancelled']:
                    terminal={'state':'cancelled'}
                    return
                slots = self.api('/slots')
                if not isinstance(slots, list) or not slots or any(not isinstance(s, dict) or type(s.get('is_processing')) is not bool for s in slots):
                    raise RuntimeError('Cannot establish server idle state')
                if not any(s['is_processing'] for s in slots):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Server is busy; restart not performed')
                self.stopping.wait(0.5)
            with self.lock:
                if self.job['cancelled'] or self.stopping.is_set():
                    terminal={'state':'cancelled'}
                    return
                self.save(state='stopping')
            self.process.stop()
            # Never start a replacement if shutdown failed to release the port.
            deadline = time.monotonic() + 30
            while self.port_open() and time.monotonic() < deadline:
                self.stopping.wait(0.25)
            if self.port_open():
                raise RuntimeError('Port still occupied after owned shutdown; replacement not started')
            if self.stopping.is_set():
                terminal={'state':'cancelled'}
                return
            self.save(state='starting')
            # Cancellation after shutdown still restores the service, without resuming agent work.
            self.process.start()
            self.wait_ready()
            if self.client_home is not None:
                configure_client_context(self, self.client_home)
            terminal={'state':'cancelled' if self.snapshot()['cancelled'] else 'ready'}
        except Exception as exc:
            terminal={'state':'failed','error':str(exc)}
        finally:
            with self.lock:
                receipt = self.directory / (hashlib.sha256(operation_id.encode()).hexdigest() + '.json')
                record={**self.job,**terminal}
                if record['state']=='ready' and record['cancelled']:
                    record['state']='cancelled'
                try:
                    # READY becomes visible only after both durable records exist.
                    publish(receipt, record)
                    publish(self.directory / 'restart.json', record)
                except OSError as exc:
                    self.persistence_error=str(exc)
                    self.job.update(state='failed',error='Could not persist terminal restart receipt')
                else:
                    self.job=record
                    self.transaction_active=False


def control_handler(supervisor, token, desktop=None, desktop_error=None):
    def public_receipt(value):
        if value is None:
            return None
        return {key:value[key] for key in ('operation_id','state','cancelled','error') if key in value}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log auth headers or checkpoint content.

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
                self.send_error(401)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 68000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                if self.path.startswith('/desktop/'):
                    if not isinstance(body, dict):
                        raise ValueError('Desktop request must be an object')
                    if self.path == '/desktop/capabilities':
                        result = {'enabled': desktop is not None, 'owner': 'existing_strata_supervisor',
                                  'recovery': 'one_native_cli_resume_then_original_desktop_session',
                                  'error_code': desktop_error}
                    elif desktop is None:
                        raise ValueError('Desktop restart is not enabled in this supervisor; configure it and restart the owner')
                    elif self.path == '/desktop/restart':
                        result = desktop.prepare(body['operation_id'], body['session_id'],
                            body['checkpoint_path'], body['caller_pid'],
                            body.get('continuation_timeout_seconds', 86400))
                    elif self.path == '/desktop/status':
                        result = desktop.status(body['operation_id'])
                    elif self.path == '/desktop/cancel':
                        result = desktop.cancel(body['operation_id'])
                    elif self.path == '/desktop/ack':
                        result = desktop.acknowledge(body['operation_id'], body['nonce'], body['session_id'])
                    else:
                        self.send_error(404)
                        return
                    data = json.dumps(result).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if (not isinstance(body,dict) or not isinstance(body.get('operation_id'),str)
                        or not 0 < len(body['operation_id']) <= 128):
                    raise ValueError('Invalid operation_id')
                if self.path == '/restart':
                    result = supervisor.request(body['operation_id'], body['checkpoint'])
                elif self.path == '/status':
                    result = supervisor.snapshot()
                    if not result or result['operation_id'] != body['operation_id']:
                        path = supervisor.directory / (hashlib.sha256(body['operation_id'].encode()).hexdigest() + '.json')
                        result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
                elif self.path == '/cancel':
                    supervisor.cancel(body['operation_id'])
                    result = {'cancelled': True}
                else:
                    self.send_error(404)
                    return
                data = json.dumps(public_receipt(result) if self.path != '/cancel' else result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (ValueError, KeyError, TypeError) as exc:
                self.send_error(400, str(exc))
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
    return Handler


def sync_client_context(home, *, server_url=None, api_key_file=None, model=None):
    """Use the already-installed client integration owner, not a second config writer."""
    state_path = home / '.claude' / 'strata-opencodex.json'
    if not state_path.is_file():
        print('Local Claude integration is not configured; remote clients must sync their own context.', flush=True)
        return
    tool = Path(__file__).with_name('strata_client_settings.py')
    if not tool.is_file():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        import re
        hook = re.search(r'"([^"\r\n]*[\\/]claude_opencodex_client\.py)"', state.get('hook_command', ''))
        if hook:
            tool = Path(hook[1]).with_name('strata_client_settings.py')
        project = state.get('maintenance_mcp', {}).get('project')
        if not tool.is_file() and not isinstance(project, str):
            raise RuntimeError('Cannot locate the installed Strata client configuration owner')
        if not tool.is_file():
            tool = Path(project) / 'tools' / 'strata_client_settings.py'
    command = [sys.executable, '-B', '-X', 'utf8', str(tool), '--sync-runtime']
    if server_url is not None:
        command += ['--server-url', server_url, '--api-key-file', str(api_key_file)]
    if model is not None:
        command += ['--expected-model', model]
    result = subprocess.run(command,
                            capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Client context sync failed; inspect the saved client settings before starting a new session: '
                           +result.stderr.decode('utf-8', errors='replace')[-2000:])
    print(result.stdout.decode('utf-8', errors='replace').strip(), flush=True)
    return json.loads(result.stdout)


def configure_client_context(supervisor, home):
    """A client configuration error must not kill work accepted by a READY server."""
    try:
        result = sync_client_context(home, server_url=supervisor.server_url,
                                     api_key_file=supervisor.key_file, model=supervisor.model)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {'status': 'failed', 'error': str(exc)[-2000:]}
        print('Strata is ready, but client context synchronization failed. Inspect client-context.json '
              'before starting a new client session; the server was kept running.', flush=True)
    else:
        result = {'status': 'synchronized' if result else 'not_configured', 'result': result}
    publish(supervisor.directory / 'client-context.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', required=True, type=Path)
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--api-key-file', required=True, type=Path)
    parser.add_argument('--token-file', required=True, type=Path)
    parser.add_argument('--model', help='Optional exact model check; otherwise discover the owned READY model')
    parser.add_argument('--server-url', default='http://127.0.0.1:8080')
    parser.add_argument('--control-port', default=8768, type=int)
    parser.add_argument('--console-log', action='store_true', help='Also display child output in the launcher console')
    parser.add_argument('--desktop-restart-config', type=Path,
                        help='Optional user opt-in for checkpointed Desktop restart/recovery')
    parser.add_argument('--fork-update-root', type=Path,
                        help='Optional NVFP4 stable-update opt-in; activates prepared bundles on owner startup only')
    parser.add_argument('--sync-client-context', action='store_true',
                        help='After each READY start/restart, sync clients to the actual local server settings')
    args = parser.parse_args()
    url = urlsplit(args.server_url)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.query or url.fragment or url.username:
        parser.error('server-url must be a local http://127.0.0.1:PORT origin')
    if not args.launcher.is_file() or not args.api_key_file.is_file():
        parser.error('Launcher and existing API key file are required')
    if args.console_log:
        print(f'Starting managed Strata. Launcher: {args.launcher.name}\n'
              f'Loading output follows. Log: {args.state_dir / "server.log"}', flush=True)
    with owner_lock(args.state_dir):
        private_directory(args.token_file.parent)
        if args.token_file.is_symlink():
            parser.error('Control token must not be a symlink')
        if not args.token_file.exists():
            with open(args.token_file, 'x', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                stream.write(secrets.token_hex(32))
        token = args.token_file.read_text(encoding='utf-8').strip()
        if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            parser.error('Invalid control token')
        updates = None
        if args.fork_update_root:
            if args.fork_update_root.resolve() != args.launcher.resolve().parent:
                parser.error('fork-update-root must be the launcher directory')
            if __package__:
                from .strata_fork_update import ForkUpdates
            else:
                from strata_fork_update import ForkUpdates
            updates = ForkUpdates(args.fork_update_root)
        supervisor = Supervisor(args.state_dir, [str(args.launcher.resolve())], args.server_url,
                                args.api_key_file, args.model, console_log=args.console_log, updates=updates,
                                client_home=Path.home() if args.sync_client_context else None)
        desktop, desktop_error = None, None
        if args.desktop_restart_config and args.desktop_restart_config.is_file():
            try:
                if __package__:
                    from .claude_desktop_runtime import DesktopRuntime, read_json
                    from .claude_desktop_restart import DesktopRestartController
                else:
                    from claude_desktop_runtime import DesktopRuntime, read_json
                    from claude_desktop_restart import DesktopRestartController
                desktop = DesktopRestartController(args.state_dir, DesktopRuntime(
                    read_json(args.desktop_restart_config)), publish_fn=publish)
            except (OSError, ValueError):
                desktop_error = 'desktop_configuration_invalid'
                print('Desktop restart recovery is disabled: inspect its saved configuration.', flush=True)
        server = ThreadingHTTPServer(('127.0.0.1', args.control_port),
                                     control_handler(supervisor, token, desktop, desktop_error))
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            supervisor.start()
            thread.start()
            if updates and updates.enabled():
                supervisor.update_worker = threading.Thread(target=supervisor.watch_updates, daemon=True)
                supervisor.update_worker.start()
            print(f'Managed Strata ready. Local control port: {args.control_port}. Log: {args.state_dir / "server.log"}', flush=True)
            while not supervisor.stopping.wait(1):
                if supervisor.process.log_error:
                    raise RuntimeError('Cannot persist server log: '+supervisor.process.log_error)
                if not supervisor.process.alive() and (not supervisor.job or supervisor.job['state'] in ('ready', 'failed', 'cancelled')):
                    raise RuntimeError('Owned server exited; automatic crash/restart loops are disabled')
        except KeyboardInterrupt:
            pass
        finally:
            supervisor.stopping.set()
            if supervisor.update_worker:
                supervisor.update_worker.join(timeout=20)
            desktop_close_error = None
            if desktop is not None:
                try:
                    desktop.close()
                except RuntimeError as exc:
                    desktop_close_error = exc
            if thread.is_alive():
                server.shutdown()
            server.server_close()
            if supervisor.worker:
                supervisor.worker.join(timeout=110)
                if supervisor.worker.is_alive():
                    raise RuntimeError('Restart worker did not settle; owned Job cleanup applies on process exit')
            supervisor.process.stop()
            supervisor.log.close()
            if desktop_close_error is not None:
                raise desktop_close_error


if __name__ == '__main__':
    main()
