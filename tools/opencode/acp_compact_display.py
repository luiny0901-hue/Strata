"""Hide ACP thought notifications without changing model input or other messages.

Opt-in transport wrapper. Input (including cancel/permission replies) is
forwarded unchanged while ACP request boundaries own CUA task approvals. Only
stdout session/update agent_thought_chunk is hidden.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
import time
from pathlib import Path


def atomic_json(path, data, replace=os.replace):
    """Readers see one complete control message, including on Windows."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    deadline = time.monotonic() + 0.5
    while True:
        try:
            replace(temporary, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.005)


class TaskState:
    """ACP transport owns task boundaries; model tool arguments cannot extend them."""
    def __init__(self, path, replace=os.replace):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.requests = {}
        self.closed = False
        self.owner = os.getpid()
        self.replace = replace
        self.publish()

    def publish(self):
        atomic_json(self.path, {'version': 1, 'owner': self.owner,
                               'tasks': list(self.requests.values())}, self.replace)

    def incoming(self, message):
        if not isinstance(message, dict):
            return
        method = message.get('method')
        params = message.get('params') or {}
        if not isinstance(params, dict):
            return
        with self.lock:
            if self.closed:
                return
            if method == 'session/prompt' and isinstance(message.get('id'), (str, int)) and isinstance(params.get('sessionId'), str):
                key = json.dumps(message['id'])
                self.requests[key] = {'key': uuid.uuid4().hex, 'sessionID': params['sessionId']}
                self.publish()
            elif method == 'session/cancel':
                self.requests = {key: task for key, task in self.requests.items()
                                 if task['sessionID'] != params.get('sessionId')}
                self.publish()

    def outgoing(self, message):
        if not isinstance(message, dict) or 'method' in message or 'id' not in message:
            return
        with self.lock:
            if self.requests.pop(json.dumps(message['id']), None) is not None:
                self.publish()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.requests.clear()
            self.publish()


def parsed(line):
    try:
        return json.loads(line)
    except (ValueError, UnicodeError):
        return None


def is_thought(line, message=None):
    if message is None:
        message = parsed(line)
    if not isinstance(message, dict) or "id" in message:
        return False
    params = message.get("params")
    update = params.get("update") if isinstance(params, dict) else None
    return (message.get("method") == "session/update"
            and isinstance(update, dict)
            and update.get("sessionUpdate") == "agent_thought_chunk")


def main():
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("Usage: acp_compact_display.py -- executable acp", file=sys.stderr)
        return 2
    directory = tempfile.TemporaryDirectory(prefix='strata-acp-task-')
    state = TaskState(Path(directory.name) / 'tasks.json')
    environment = {**os.environ, 'STRATA_CUA_TASK_STATE': str(state.path)}
    child = subprocess.Popen(command, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=None, env=environment)
    output_lock = threading.Lock()
    approvals = {}
    approval_lock = threading.Lock()
    def emit(message):
        with output_lock:
            sys.stdout.buffer.write((json.dumps(message, ensure_ascii=False)+'\n').encode('utf-8'))
            sys.stdout.buffer.flush()
    def approval_loop():
        root = Path(directory.name)
        while not state.closed:
            with approval_lock:
                for rpc_id, (path, _) in list(approvals.items()):
                    if not path.exists():
                        approvals.pop(rpc_id, None)
            for path in root.glob('approval-*.request'):
                try:
                    request = json.loads(path.read_text(encoding='utf-8'))
                    rpc_id = 'strata-cua-approval-' + path.stem
                    with approval_lock:
                        if rpc_id in approvals:
                            continue
                    with state.lock:
                        owned = any(t['key'] == request.get('taskKey') and t['sessionID'] == request.get('sessionID') for t in state.requests.values())
                    if not owned:
                        continue
                    with approval_lock:
                        approvals[rpc_id] = (path, request)
                    emit({'jsonrpc':'2.0','id':rpc_id,'method':'session/request_permission','params':{
                        'sessionId':request['sessionID'],
                        'toolCall':{'toolCallId':rpc_id,'title':'CUA 현재 작업 전체 승인','kind':'other','status':'pending',
                                    'content':[{'type':'content','content':{'type':'text','text':request['preview']}}]},
                        'options':[{'optionId':'deny','kind':'reject_once','name':'허용 안 함'},
                                   {'optionId':'task','kind':'allow_once','name':'현재 작업 완료까지 허용'}]}})
                except (OSError, ValueError, KeyError):
                    continue
            time.sleep(0.05)
    approval_thread = threading.Thread(target=approval_loop, daemon=True)
    approval_thread.start()
    def relay_input():
        try:
            for line in sys.stdin.buffer:
                message = parsed(line)
                if isinstance(message, dict) and str(message.get('id','')).startswith('strata-cua-approval-') and 'method' not in message:
                    with approval_lock:
                        entry = approvals.get(message['id'])
                        if entry:
                            path, request = entry
                            outcome = (message.get('result') or {}).get('outcome') or {}
                            accepted = outcome.get('outcome') == 'selected' and outcome.get('optionId') == 'task'
                            with state.lock:
                                accepted = accepted and any(t['key'] == request.get('taskKey') and t['sessionID'] == request.get('sessionID') for t in state.requests.values())
                            # Remove the request before releasing its in-flight ID.
                            # The discovery thread must never re-emit a consumed approval.
                            path.unlink(missing_ok=True)
                            atomic_json(path.with_suffix('.response'), {'accepted':bool(accepted)})
                            approvals.pop(message['id'], None)
                    continue
                state.incoming(message)
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            print(f'ACP input relay closed: {type(error).__name__}: {error}', file=sys.stderr)
        finally:
            state.close()
            try:
                child.stdin.close()
            except (OSError, ValueError):
                pass
    threading.Thread(target=relay_input, daemon=True).start()
    try:
        for line in child.stdout:
            message = parsed(line)
            state.outgoing(message)
            if not is_thought(line, message):
                with output_lock:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
        return child.wait()
    except (BrokenPipeError, KeyboardInterrupt):
        return 1
    finally:
        state.close()
        child.stdout.close()
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        approval_thread.join(timeout=1)
        directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
