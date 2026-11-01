"""Small MCP adapter to the existing Strata supervisor; owns no inference process."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    from . import claude_opencodex_client as shared
    from .strata_mcp import McpServer, ToolError, check_schema
else:
    import claude_opencodex_client as shared
    from strata_mcp import McpServer, ToolError, check_schema


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ControlRejected(ToolError):
    """A known rejection must not cancel a previous operation with the same ID."""


class MaintenanceTools:
    def __init__(self, control_url, token_file, *, home=None):
        parsed = urlsplit(control_url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment):
            raise ValueError('Supervisor control must be a loopback HTTP origin')
        self.control_url = control_url.rstrip('/')
        self.token_file = Path(token_file)
        self.home = home or Path.home()
        self.local = threading.local()
        self.opener = build_opener(NoRedirect())

    def defs(self):
        op = {'type': 'string', 'minLength': 1, 'maxLength': 128,
              'pattern': '[a-zA-Z0-9_.-]+', 'description': 'Stable unique operation ID; reuse after uncertain delivery.'}
        ro = {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}
        request_log_options = {
            'include_opencodex_requests': {'type': 'boolean',
                'description': 'Opt in to a bounded, sanitized OpenCodex log query; false/omitted starts no CLI process.'},
            'request_window': {'type': 'string', 'enum': ['15m', '1h'],
                'description': 'OpenCodex Claude log lookback used only when include_opencodex_requests is true.'}}
        tools = []
        for name, description, properties, required, annotation in [
            ('environment_status', 'Read Claude/OpenCodex configuration, live Strata health/activity, device-wide GPU/RAM, route preview, recent latency/failure categories and partial provider pacing. These observations do not prove workload fit or complete gateway idleness. Optional logs run one read-only CLI query (12 records, 8 seconds, 128 KiB), omit content/credentials and group CLI/Desktop. A terminal close reason means body EOF, not Desktop completion.', request_log_options, [], ro),
            ('opencodex_service_status', 'Read the recorded OpenCodex service owner through its exact Bun/CLI and official passive `service status --json` command. Returns only whitelisted state and runtime identity fields; never returns tokens or attestation secrets. Does not start, stop, repair, or restart the service.', {}, [], ro),
            ('restart_strata', 'After an authorized saved Strata change, await the EXISTING supervisor restart. Save completed/unfinished work and paths first. Same operation_id/checkpoint is idempotent. Waits for idle up to the supervisor deadline; never kills a busy server, OpenCodex or Desktop. Cancellation/timeout requests cancel and requires receipt inspection.',
             {'operation_id': op, 'checkpoint': {'type': 'string', 'minLength': 1, 'maxLength': 16000,
                 'description': 'Single-line saved scope, completed/remaining work, exact paths, pending validation. No secrets.'},
              'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 900}},
             ['operation_id', 'checkpoint'], {'destructiveHint': True, 'idempotentHint': True, 'openWorldHint': False}),
            ('restart_status', 'Read one existing supervisor receipt using its original operation_id; does not submit or repeat a restart.', {'operation_id': op}, ['operation_id'], ro),
            ('cancel_restart', 'Cancel this operation_id through the existing supervisor, including uncertain delivery. Does not roll back saved source/configuration.', {'operation_id': op}, ['operation_id'], {'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False})]:
            tools.append({'name': name, 'description': description, 'inputSchema': {'type': 'object',
                'properties': properties, 'required': required, 'additionalProperties': False}, 'annotations': annotation})
        session = {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                   'description': 'Exact current native Claude Code session_id from SessionStart; not the local_ Desktop ID.'}
        desktop = [
            ('restart_desktop', 'Submit one durable checkpointed Desktop restart to the EXISTING external supervisor. Save the checkpoint inside this session project first. After accepted, finish this turn; do not wait/poll in the original turn. The owner waits for this tool result and end_turn, normally quits Desktop, runs the same installed Claude Code once with --resume, then reopens the exact Desktop conversation. Preserves model/effort/permission mode. If 3p entry links are disabled, uses configured background CUA for one unique sidebar button and verifies the exact session focus. No physical mouse/keyboard input or foreground escalation. Same operation_id is never replayed. Runtime is opt-in Windows only.',
             {'operation_id': op, 'session_id': session,
              'checkpoint_path': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
              'continuation_timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 86400}},
             ['operation_id', 'session_id', 'checkpoint_path'], {'destructiveHint': True, 'idempotentHint': True, 'openWorldHint': False}),
            ('desktop_restart_status', 'Read an existing Desktop handoff receipt without repeating it. Omit operation_id to read whether the external owner supports Desktop recovery. ready means lifecycle handoff completed, not the entire user project completed.',
             {'operation_id': op}, [], ro),
            ('cancel_desktop_restart', 'Explicitly cancel this Desktop handoff. Before quit, do not change the app. After quit, restore the app and stop/skip only the owned recovery execution. Saved file changes are not rolled back.',
             {'operation_id': op}, ['operation_id'], {'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}),
            ('acknowledge_desktop_restart', 'Only in the recovery request: after reading its saved checkpoint and checking actual files, acknowledge the exact operation/nonce/current native session. Does not mark the user task complete. A cancelled or mismatched handoff is rejected.',
             {'operation_id': op, 'session_id': session, 'nonce': {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}},
             ['operation_id', 'session_id', 'nonce'], {'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False})]
        for name, description, properties, required, annotation in desktop:
            tools.append({'name': name, 'description': description, 'inputSchema': {'type': 'object',
                'properties': properties, 'required': required, 'additionalProperties': False}, 'annotations': annotation})
        return tools

    def post(self, route, body):
        token = self.token_file.read_text(encoding='utf-8-sig').strip()
        if not re.fullmatch('[a-f0-9]{64}', token):
            raise ToolError('Invalid existing supervisor token file; no request was sent')
        request = Request(self.control_url+route, data=json.dumps(body).encode('utf-8'),
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20 if route == '/desktop/restart' else 5) as response:
                raw = response.read(256*1024+1)
        except HTTPError as exc:
            exc.close()
            if exc.code in (400, 401, 403):
                raise ControlRejected(f'Supervisor rejected {route}: HTTP {exc.code}; preserve the original operation') from None
            raise ToolError(f'Supervisor {route}: HTTP {exc.code}; inspect the original operation receipt') from None
        if len(raw) > 256*1024:
            raise ToolError('Supervisor response exceeded 256 KiB; inspect original receipt')
        return json.loads(raw)

    def call(self, name, args):
        definition = next((d for d in self.defs() if d['name'] == name), None)
        if not definition:
            raise KeyError(name)
        args = check_schema(definition['inputSchema'], dict(args) if isinstance(args, dict) else args)
        if any(not value.strip() for value in args.values() if isinstance(value, str)):
            raise ToolError('Operation ID and checkpoint must not be blank')
        try:
            if name == 'environment_status':
                report = shared.diagnose(self.home)
                observation_started = time.monotonic()
                runtime_status = shared.strata_runtime_status(self.home, timeout=1)
                report['strata_runtime'] = runtime_status
                remaining = max(0.2, 3-(time.monotonic()-observation_started))
                report['strata_activity'] = shared.strata_activity(
                    self.home, timeout=remaining, runtime_status=runtime_status)
                if args.get('include_opencodex_requests') is True:
                    report['opencodex_recent_requests'] = self.opencodex_recent_requests(
                        args.get('request_window', '15m'))
                return report
            if name == 'opencodex_service_status':
                return self.opencodex_service_status()
            if name == 'restart_desktop':
                cancelled = getattr(self.local, 'cancelled', threading.Event())
                explicit = getattr(self.local, 'explicit_cancelled', cancelled)
                if cancelled.is_set():
                    if explicit.is_set():
                        try:
                            self.post('/desktop/cancel', {'operation_id': args['operation_id']})
                        except Exception:
                            pass
                    raise ToolError('Cancelled before Desktop handoff submission')
                rejected = False
                try:
                    receipt = self.post('/desktop/restart', {**args, 'caller_pid': os.getpid()})
                except ControlRejected:
                    rejected = True
                    raise
                finally:
                    # Intentional Desktop/MCP EOF is not a cancellation of the
                    # externally accepted transaction. Human Stop remains one.
                    if explicit.is_set() and not rejected:
                        try:
                            self.post('/desktop/cancel', {'operation_id': args['operation_id']})
                        except Exception:
                            pass
                if explicit.is_set():
                    raise ToolError('Desktop handoff cancellation requested; inspect the original receipt')
                return {**receipt, 'summary': 'Checkpointed Desktop handoff accepted. Finish this turn now. The external owner waits for its persisted end_turn before quitting; do not submit another restart or poll while this turn remains open.'}
            if name == 'desktop_restart_status':
                if args.get('operation_id'):
                    return self.post('/desktop/status', args)
                capabilities = self.post('/desktop/capabilities', {})
                if capabilities.get('enabled'):
                    try:
                        if __package__:
                            from .claude_desktop_runtime import CONFIG_RELATIVE, DesktopRuntime, read_json
                        else:
                            from claude_desktop_runtime import CONFIG_RELATIVE, DesktopRuntime, read_json
                        runtime = DesktopRuntime(read_json(self.home/CONFIG_RELATIVE), home=self.home)
                        capabilities['current_session_id'] = runtime.current_session_id(os.getpid())
                        capabilities['current_session_status'] = 'identified_from_caller_ancestry'
                    except (OSError, ValueError, subprocess.SubprocessError):
                        capabilities['current_session_status'] = 'not_identified'
                return capabilities
            if name == 'cancel_desktop_restart':
                return self.post('/desktop/cancel', args)
            if name == 'acknowledge_desktop_restart':
                return self.post('/desktop/ack', args)
            operation = args['operation_id']
            if name == 'restart_status':
                receipt = self.post('/status', {'operation_id': operation})
                if receipt is not None and receipt.get('operation_id') != operation:
                    raise ToolError('Supervisor receipt belongs to another operation')
                return receipt or {'operation_id': operation, 'state': 'unknown'}
            if name == 'cancel_restart':
                return self.post('/cancel', {'operation_id': operation})
            return self.restart(args)
        except ToolError:
            raise
        except (OSError, ValueError) as exc:
            raise ToolError(f'Maintenance request failed ({type(exc).__name__}); inspect the saved state before retrying') from None

    def _registered_opencodex_owner(self):
        """Resolve the recorded owner for passive CLI queries; never search PATH."""
        configured_home = Path(self.home)/'.opencodex'
        try:
            owner = json.loads((configured_home/'service-state.json').read_text(encoding='utf-8-sig'))
        except FileNotFoundError:
            return None, {'status': 'not_configured', 'ready': False,
                          'scope': 'No OpenCodex service owner is registered for this user.'}
        except (OSError, ValueError):
            return None, {'status': 'invalid_owner_state', 'ready': False,
                          'scope': 'The installed service owner record could not be read; no command was run.'}
        if not isinstance(owner, dict):
            return None, {'status': 'invalid_owner_state', 'ready': False,
                          'scope': 'The installed service owner record is not an object; no command was run.'}
        try:
            bun = Path(owner['bunPath']).expanduser()
            cli = Path(owner['cliPath']).expanduser()
            owner_home = Path(owner.get('opencodexHome') or configured_home).expanduser()
        except (KeyError, TypeError, ValueError):
            return None, {'status': 'invalid_owner_state', 'ready': False,
                          'scope': 'The installed service owner record is incomplete; no command was run.'}
        if not bun.is_absolute() or not cli.is_absolute() or not owner_home.is_absolute():
            return None, {'status': 'invalid_owner_state', 'ready': False,
                          'scope': 'The installed service owner paths must be absolute; no command was run.'}
        if not bun.is_file() or not cli.is_file():
            return None, {'status': 'owner_files_missing', 'ready': False,
                          'scope': 'The recorded Bun or OpenCodex CLI is unavailable; no command was run.'}
        return {'owner': owner, 'bun': bun, 'cli': cli, 'home': owner_home}, None

    def opencodex_recent_requests(self, window):
        """Read a bounded log snapshot and emit only validated performance fields."""
        registered, failure = self._registered_opencodex_owner()
        if failure:
            return {'status': failure['status'], 'requests': [], 'scope': failure['scope']}
        owner, bun, cli, owner_home = (registered[key] for key in ('owner', 'bun', 'cli', 'home'))
        env = dict(os.environ)
        env['OPENCODEX_HOME'] = str(owner_home)
        if isinstance(owner.get('codexHome'), str) and owner['codexHome']:
            env['CODEX_HOME'] = owner['codexHome']
        command = [str(bun), str(cli), 'logs', 'filter', '--surface', 'claude',
                   '--time-window', window, '--limit', '12', '--json']
        output = bytearray()
        output_limit = 131072
        overflow = threading.Event()
        read_errors = []
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0, env=env)
        except OSError as exc:
            return {'status': 'status_command_failed', 'requests': [], 'error': type(exc).__name__,
                    'scope': 'The recorded OpenCodex log command could not run; no service action was taken.'}

        def collect_stdout():
            try:
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        return
                    remaining = output_limit + 1 - len(output)
                    if remaining > 0:
                        output.extend(chunk[:remaining])
                    if len(output) > output_limit:
                        overflow.set()
                        try:
                            process.kill()
                        except OSError:
                            pass
                        return
            except (OSError, ValueError) as exc:
                read_errors.append(type(exc).__name__)

        reader = threading.Thread(target=collect_stdout, name='opencodex-log-reader', daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        finally:
            reader.join(timeout=2)
            if reader.is_alive():
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.stdout.close()
                except (OSError, ValueError):
                    pass
                reader.join(timeout=1)
            try:
                process.stdout.close()
            except (OSError, ValueError):
                pass
        if overflow.is_set():
            return {'status': 'invalid_status_response', 'requests': [],
                    'scope': 'The OpenCodex log response exceeded the 128 KiB limit; the query was stopped.'}
        if timed_out:
            return {'status': 'status_command_timeout', 'requests': [],
                    'scope': 'The bounded OpenCodex log query timed out.'}
        if read_errors:
            return {'status': 'status_command_failed', 'requests': [], 'error': read_errors[0],
                    'scope': 'The OpenCodex log response could not be read completely.'}
        stdout = output.decode('utf-8', errors='replace')
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError):
            return {'status': 'invalid_status_response', 'requests': [],
                    'scope': 'The OpenCodex log command did not return valid JSON.'}
        if (process.returncode != 0 or not isinstance(payload, dict)
                or payload.get('schemaVersion') != 1 or not isinstance(payload.get('logs'), list)):
            return {'status': 'status_command_failed' if process.returncode else 'invalid_status_response',
                    'exit_code': process.returncode, 'requests': [],
                    'scope': 'The OpenCodex log command returned an unsupported or unsuccessful response.'}

        def bounded_int(value, maximum=1_000_000_000_000):
            return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum else None

        efforts = {'none', 'default', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}
        close_reasons = {'terminal', 'client_cancel', 'body_stall', 'body_overflow'}
        summaries = []
        for row in payload['logs'][:12]:
            if not isinstance(row, dict):
                continue
            summary = {}
            timestamp = bounded_int(row.get('timestamp'), 10_000_000_000_000)
            if timestamp is not None:
                summary['timestamp_ms'] = timestamp
            effort = row.get('requestedEffort')
            if isinstance(effort, str):
                summary['requested_effort'] = effort.lower() if effort.lower() in efforts else 'other'
            status = bounded_int(row.get('status'), 599)
            if status is not None and status >= 100:
                summary['http_status'] = status
            for source, target in (('durationMs', 'duration_ms'), ('firstOutputMs', 'first_output_ms'),
                                   ('genStartMs', 'generation_start_ms'), ('lastOutputMs', 'last_output_ms')):
                value = bounded_int(row.get(source), 86_400_000)
                if value is not None:
                    summary[target] = value
            close_reason = row.get('closeReason')
            if isinstance(close_reason, str):
                summary['close_reason'] = close_reason if close_reason in close_reasons else 'other'
            usage = row.get('usage')
            if isinstance(usage, dict):
                safe_usage = {}
                for source, target in (('inputTokens', 'input_tokens'),
                                       ('cacheReadInputTokens', 'cache_read_input_tokens'),
                                       ('cacheCreationInputTokens', 'cache_creation_input_tokens'),
                                       ('outputTokens', 'output_tokens'), ('totalTokens', 'total_tokens')):
                    value = bounded_int(usage.get(source))
                    if value is not None:
                        safe_usage[target] = value
                if safe_usage:
                    summary['usage'] = safe_usage
            summary['message_stop_evidence'] = 'not_recorded'
            summaries.append(summary)

        counts = payload.get('window') if isinstance(payload.get('window'), dict) else {}
        window_counts = {}
        for key in ('loaded', 'matched', 'returned', 'limit'):
            value = bounded_int(counts.get(key), 1_000_000)
            if value is not None:
                window_counts[key] = value
        return {'status': 'observed', 'surface_filter': 'claude', 'time_window': window,
                'window_counts': window_counts, 'requests': summaries,
                'scope': 'Claude CLI and Desktop are grouped; correlate timestamps with the UI. Only allowlisted timing, status and usage fields are returned. close_reason=terminal is body EOF, not proof of Anthropic message_stop or Desktop completion.'}

    def opencodex_service_status(self):
        """Query only the installed owner; never expose runtime credentials."""
        registered, failure = self._registered_opencodex_owner()
        if failure:
            return failure
        owner, bun, cli, owner_home = (registered[key] for key in ('owner', 'bun', 'cli', 'home'))

        env = dict(os.environ)
        env['OPENCODEX_HOME'] = str(owner_home)
        if isinstance(owner.get('codexHome'), str) and owner['codexHome']:
            env['CODEX_HOME'] = owner['codexHome']
        try:
            result = subprocess.run([str(bun), str(cli), 'service', 'status', '--json'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace', timeout=15, check=False, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'status': 'status_command_failed', 'ready': False, 'error': type(exc).__name__,
                    'scope': 'The recorded owner status command failed; no service action was taken.'}
        if len(result.stdout.encode('utf-8', errors='replace')) > 65536:
            return {'status': 'invalid_status_response', 'ready': False,
                    'scope': 'The owner status response exceeded 64 KiB; no service action was taken.'}
        try:
            status = json.loads(result.stdout)
        except (TypeError, ValueError):
            return {'status': 'invalid_status_response', 'ready': False, 'exit_code': result.returncode,
                    'scope': 'The owner did not return valid JSON; no service action was taken.'}
        if result.returncode != 0 or not isinstance(status, dict):
            return {'status': 'status_command_failed', 'ready': False, 'exit_code': result.returncode,
                    'scope': 'The owner status command returned an error; no service action was taken.'}

        serving = status.get('serving') if isinstance(status.get('serving'), dict) else {}
        identity = {}
        port = serving.get('port')
        try:
            runtime_port = json.loads((owner_home/'runtime-port.json').read_text(encoding='utf-8-sig'))
            if isinstance(runtime_port, dict):
                pid = runtime_port.get('pid')
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                    identity['pid'] = pid
                candidate_port = runtime_port.get('port')
                if isinstance(candidate_port, int) and not isinstance(candidate_port, bool) and 0 < candidate_port < 65536:
                    port = candidate_port
        except (OSError, ValueError):
            pass
        runtime_rows = []
        try:
            runtimes = json.loads((owner_home/'serving-runtimes.json').read_text(encoding='utf-8-sig')).get('runtimes', [])
            if isinstance(runtimes, list):
                for runtime in runtimes[:8]:
                    if not isinstance(runtime, dict):
                        continue
                    row = {}
                    if isinstance(runtime.get('version'), str):
                        row['version'] = runtime['version'][:96]
                    if isinstance(runtime.get('servedAt'), str):
                        row['served_at'] = runtime['servedAt'][:64]
                    if row:
                        runtime_rows.append(row)
        except (OSError, ValueError, AttributeError):
            pass
        if runtime_rows:
            identity['runtimes'] = runtime_rows

        ready = (status.get('supported') is True and status.get('installed') is True
                 and status.get('enabled') is True and status.get('running') is True
                 and status.get('viable') is True and status.get('stale') is False
                 and status.get('conflict') is False and serving.get('probed') is True
                 and serving.get('ok') is True)
        return {'status': 'ready' if ready else 'not_ready', 'ready': ready,
                'backend': status.get('backend') if isinstance(status.get('backend'), str) else None,
                'label': status.get('label') if isinstance(status.get('label'), str) else None,
                'installed': status.get('installed') is True, 'enabled': status.get('enabled') is True,
                'running': status.get('running') is True, 'viable': status.get('viable') is True,
                'stale': status.get('stale') is True, 'conflict': status.get('conflict') is True,
                'serving': {'probed': serving.get('probed') is True, 'ok': serving.get('ok') is True,
                            'port': port if isinstance(port, int) and not isinstance(port, bool) else None},
                'runtime_identity': identity,
                'restart_command': [str(bun), str(cli), 'service', 'restart'],
                'scope': 'Official owner status and sanitized runtime identity only. The restart command identifies the registered owner path; it is not an authorization to restart. Compare PID/served_at before and after an authorized restart; never retry an uncertain restart blindly.'}

    def restart(self, args):
        cancelled = getattr(self.local, 'cancelled', threading.Event())
        if cancelled.is_set():
            raise ToolError('Cancelled before restart submission')
        deadline = time.monotonic()+args.get('timeout_seconds', 900)
        operation = args['operation_id']
        submitted = False
        try:
            submitted = True  # A failed HTTP response never proves the request was not accepted.
            receipt = self.post('/restart', {'operation_id': operation, 'checkpoint': args['checkpoint']})
            while True:
                if cancelled.is_set():
                    raise ToolError('Restart wait cancelled; inspect the original operation receipt')
                if not isinstance(receipt, dict) or receipt.get('operation_id') != operation:
                    raise ToolError('Supervisor receipt missing or belongs to another operation')
                state = receipt.get('state')
                if receipt.get('cancelled') is True:
                    raise ToolError('Strata restart cancelled; unfinished work is not complete')
                if state in ('ready', 'failed', 'cancelled'):
                    if state != 'ready':
                        raise ToolError(f'Strata restart {state}; unfinished work is not complete')
                    return {**receipt, 'summary': 'Existing supervisor confirmed Strata model readiness. Verify current files and continue only the saved unfinished work.'}
                if state not in ('queued', 'draining', 'stopping', 'starting'):
                    raise ToolError('Unknown supervisor state; inspect saved receipt')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise ToolError('Restart wait timed out; inspect original operation receipt')
                cancelled.wait(min(0.5, remaining))
                receipt = self.post('/status', {'operation_id': operation})
        except ControlRejected:
            raise
        except Exception:
            if submitted:
                try:
                    self.post('/cancel', {'operation_id': operation})
                except Exception:
                    pass  # Preserve uncertain delivery; never create a replacement operation.
            raise


class MaintenanceMcp(McpServer):
    """Reuse Strata's stdio implementation; add request cancellation for this adapter only."""
    def __init__(self, tools, out):
        super().__init__(None, out)
        self.tools = tools
        self.active = {}
        self.explicit_active = {}
        self.cancelled = set()
        self.closing = threading.Event()
        self.active_lock = threading.Lock()

    def handle(self, message):
        if (isinstance(message, dict) and message.get('jsonrpc') == '2.0' and 'id' not in message
                and message.get('method') == 'notifications/cancelled'):
            params = message.get('params')
            request_id = params.get('requestId') if isinstance(params, dict) else None
            if type(request_id) not in (int, str):
                return None
            with self.active_lock:
                event = self.active.get(request_id)
                if event:
                    event.set()
                    explicit = self.explicit_active.get(request_id)
                    if explicit is not None:
                        explicit.set()
                elif isinstance(request_id, (int, str)):
                    if len(self.cancelled) >= 256:
                        self.cancelled.pop()
                    self.cancelled.add(request_id)
            return None
        call = isinstance(message, dict) and message.get('method') == 'tools/call' and 'id' in message
        if call and type(message['id']) not in (int, str):
            return self.error(None, -32600, 'invalid request id')
        event = threading.Event()
        explicit = threading.Event()
        if call:
            with self.active_lock:
                if message['id'] in self.active:
                    return self.error(message['id'], -32600,
                                      'duplicate active request id; request was not dispatched')
                self.active[message['id']] = event
                self.explicit_active[message['id']] = explicit
                if message['id'] in self.cancelled or self.closing.is_set():
                    if message['id'] in self.cancelled:
                        explicit.set()
                    self.cancelled.discard(message['id'])
                    event.set()
            self.tools.local.cancelled = event
            self.tools.local.explicit_cancelled = explicit
        try:
            response = super().handle(message)
            if isinstance(message, dict) and message.get('method') == 'initialize' and response and 'result' in response:
                response['result']['serverInfo'] = {'name': 'strata-maintenance', 'version': '1.3.0'}
                response['result']['instructions'] = (
                    'Use only for requested Claude Desktop Code/OpenCodex/Strata maintenance. '
                    'Read environment_status first. Before lifecycle changes, read '
                    f'{(self.tools.home/".claude/guidance/maintenance.md").as_posix()}. '
                    'GPU/RAM is device-wide; Strata activity and provider pacing omit some queued/other-client work. '
                    'Prove idleness before restart. Restart Strata through its existing supervisor with a saved '
                    'checkpoint and operation_id. For an authorized OpenCodex restart, use opencodex_service_status '
                    'and its exact owner command; verify runtime change and health afterward. Inspect uncertain '
                    'delivery before retrying. For an authorized Desktop restart, check desktop_restart_status '
                    'capabilities, save a project checkpoint and use restart_desktop once. After acceptance finish '
                    'the original turn. The external owner performs one native CLI resume while Desktop is closed '
                    'and then reopens the original conversation. A receipt is not proof of complete user work. '
                    'Never kill processes or repair/install services implicitly.')
            return response
        finally:
            if call:
                with self.active_lock:
                    self.active.pop(message['id'], None)
                    self.explicit_active.pop(message['id'], None)

    def serve(self, stream):
        def lines():
            try:
                yield from stream
            finally:
                self.closing.set()
                with self.active_lock:
                    for event in self.active.values():
                        event.set()
        return super().serve(lines())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-url', required=True)
    parser.add_argument('--token-file', required=True, type=Path)
    args = parser.parse_args()
    server = MaintenanceMcp(MaintenanceTools(args.control_url, args.token_file), sys.stdout.buffer)
    server.serve(sys.stdin.buffer)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
