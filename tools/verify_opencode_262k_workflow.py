#!/usr/bin/env python3
"""Exercise a bounded OpenCode work-and-follow-up session against a local fake model.

The verifier never contacts Strata or starts a model.  It gives OpenCode an
OpenAI-compatible loopback endpoint with a declared context limit and records
requests so the session and compaction policy can be inspected.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.configure_opencode_session_recovery import DEFAULT_CONTEXT, compaction_policy

MODEL_ID = "workflow-fixture"
CONTEXT_LIMIT = DEFAULT_CONTEXT
COMPACTION_KEEP = compaction_policy(CONTEXT_LIMIT)["keep"]
COMPACTION_BUFFER = compaction_policy(CONTEXT_LIMIT)["buffer"]
COMPACTION_TRIGGER = compaction_policy(CONTEXT_LIMIT)["trigger"]
OUTPUT_LIMIT = min(32_000, max(1_024, CONTEXT_LIMIT // 4))


def configure_context(context: int) -> None:
    """Apply one isolated fixture context before the loopback server starts."""
    global CONTEXT_LIMIT, COMPACTION_KEEP, COMPACTION_BUFFER, COMPACTION_TRIGGER, OUTPUT_LIMIT
    policy = compaction_policy(context)
    CONTEXT_LIMIT = context
    COMPACTION_KEEP = policy["keep"]
    COMPACTION_BUFFER = policy["buffer"]
    COMPACTION_TRIGGER = policy["trigger"]
    OUTPUT_LIMIT = min(32_000, max(1_024, context // 4))


class FakeOpenAiServer(ThreadingHTTPServer):
    """Small deterministic OpenAI-compatible endpoint used only by this verifier."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeOpenAiHandler)
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []
        self.report_large_initial_turn = True
        self.confirmation_command: str | None = None
        self.confirmation_phase = "idle"
        self.lock = threading.Lock()


class FakeOpenAiHandler(BaseHTTPRequestHandler):
    server: FakeOpenAiServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _completion(
        self,
        number: int,
        request: dict[str, Any],
        tool_call: dict[str, Any] | None = None,
        prompt_tokens: int = 1,
        content: str | None = None,
    ) -> None:
        payload = {
            "id": f"fixture-{number}",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content or f"FIXTURE_REPLY_{number}"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 1, "total_tokens": prompt_tokens + 1},
        }
        if tool_call:
            payload["choices"][0]["message"] = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
            payload["choices"][0]["finish_reason"] = "tool_calls"
        if not request.get("stream"):
            self._json(payload)
            return

        first_delta: dict[str, Any] = {"role": "assistant"}
        if tool_call:
            first_delta["tool_calls"] = [{"index": 0, **tool_call}]
        else:
            first_delta["content"] = payload["choices"][0]["message"]["content"]
        chunks = [
            {
                "id": payload["id"],
                "object": "chat.completion.chunk",
                "created": 0,
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": first_delta, "finish_reason": None}],
            },
            {
                "id": payload["id"],
                "object": "chat.completion.chunk",
                "created": 0,
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool_call else "stop"}],
                "usage": payload["usage"],
            },
        ]
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode("utf-8") + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        with self.server.lock:
            self.server.paths.append(f"GET {self.path}")
        if self.path == "/v1/models":
            self._json({"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        with self.server.lock:
            self.server.paths.append(f"POST {self.path}")
        if self.path != "/v1/chat/completions":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        with self.server.lock:
            self.server.requests.append(request)
            number = len(self.server.requests)

        messages = request.get("messages", [])
        tools = request.get("tools", [])
        latest_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if isinstance(latest_user, list):
            latest_user = json.dumps(latest_user)
        if "<template>" in str(latest_user) or "summary template" in str(latest_user):
            self._completion(
                number,
                request,
                prompt_tokens=1,
                content=(
                    "## Objective\n- Verify fixture workflow\n\n"
                    "## Constraints\n- (none)\n\n"
                    "## Decisions\n- Use a loopback fixture\n\n"
                    "## Work State\n### Completed\n- Initial write\n\n"
                    "### Active\n- (none)\n\n"
                    "### Blocked\n- (none)\n\n"
                    "## Next Move\n1. Apply follow-up edit\n\n"
                    "## Relevant Files\n- `workflow.txt`: fixture output\n\n"
                    "## Important Context\n- 262K policy fixture\n"
                ),
            )
            return
        confirmation_workflow = "WAIT_FOR_CONFIRMATION" in json.dumps(messages)
        if confirmation_workflow and tools:
            if messages and messages[-1].get("role") == "user" and self.server.confirmation_phase == "idle":
                if not self.server.confirmation_command:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self.server.confirmation_phase = "waiting"
                self._completion(
                    number,
                    request,
                    {
                        "id": f"call-confirm-{number}",
                        "type": "function",
                        "function": {
                            "name": "shell",
                            "arguments": json.dumps(
                                {
                                    "command": self.server.confirmation_command,
                                    "description": "Wait for the isolated confirmation fixture",
                                    "timeout": 10_000,
                                }
                            ),
                        },
                    },
                )
                return
            if messages and messages[-1].get("role") == "tool" and self.server.confirmation_phase == "waiting":
                self.server.confirmation_phase = "continued"
                self._completion(
                    number,
                    request,
                    {
                        "id": f"call-continue-{number}",
                        "type": "function",
                        "function": {
                            "name": "write",
                            "arguments": json.dumps(
                                {"path": "confirmation-follow-up.txt", "content": "continued after confirmation\n"}
                            ),
                        },
                    },
                )
                return
            if messages and messages[-1].get("role") == "tool" and self.server.confirmation_phase == "continued":
                self.server.confirmation_phase = "completed"
                self._completion(number, request)
                return
        if tools and messages and messages[-1].get("role") == "user":
            revised = "REVISE_WORKFLOW" in str(latest_user)
            content = "revised by follow-up\n" if revised else "created by initial task\n"
            self._completion(
                number,
                request,
                {
                    "id": f"call-write-{number}",
                    "type": "function",
                    "function": {
                        "name": "write",
                        "arguments": json.dumps({"path": "workflow.txt", "content": content}),
                    },
                },
            )
            return
        large_initial_turn = False
        if messages and messages[-1].get("role") == "tool":
            with self.server.lock:
                large_initial_turn = self.server.report_large_initial_turn
                self.server.report_large_initial_turn = False
        self._completion(number, request, prompt_tokens=COMPACTION_TRIGGER if large_initial_turn else 1)


def write_config(workdir: Path, base_url: str) -> Path:
    # Project configuration has higher precedence than the user's global
    # configuration, including on Windows builds that still discover ~/.config
    # when XDG_CONFIG_HOME is set.
    config = workdir / "opencode.json"
    config.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "model": f"fixture/{MODEL_ID}",
                "providers": {
                    "fixture": {
                        "name": "OpenCode 262K workflow fixture",
                        "package": "@opencode/ai/providers/openai-compatible",
                        "settings": {"baseURL": base_url, "apiKey": "fixture-only"},
                        "models": {
                            MODEL_ID: {
                                "name": "Workflow fixture 262K",
                                "limit": {"context": CONTEXT_LIMIT, "output": OUTPUT_LIMIT},
                                "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                            }
                        },
                    }
                },
                "agents": {"build": {"steps": 60}},
                "compaction": {
                    "auto": True,
                    "keep": {"tokens": COMPACTION_KEEP},
                    "buffer": COMPACTION_BUFFER,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def run_opencode(command: list[str], workdir: Path, sandbox_root: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(sandbox_root / "config")
    environment["XDG_DATA_HOME"] = str(sandbox_root / "data")
    environment["XDG_STATE_HOME"] = str(sandbox_root / "state")
    environment["XDG_CACHE_HOME"] = str(sandbox_root / "cache")
    environment["OPENCODE_CONFIG"] = str(workdir / "opencode.json")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        cwd=workdir,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(timeout=25)
    except subprocess.TimeoutExpired as error:
        # --standalone starts a private server.  Stop only this exact child
        # tree; never touch the user's background OpenCode or Strata process.
        subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"], capture_output=True, text=True, check=False)
        stdout, stderr = process.communicate(timeout=5)
        raise subprocess.TimeoutExpired(error.cmd, error.timeout, output=stdout, stderr=stderr) from error
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def request_shapes(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return protocol evidence without retaining full user prompts or tool output."""
    shapes = []
    for request in requests:
        tools = request.get("tools", [])
        write = next((tool.get("function", {}) for tool in tools if tool.get("function", {}).get("name") == "write"), {})
        latest_user = next((message.get("content", "") for message in reversed(request.get("messages", [])) if message.get("role") == "user"), "")
        if isinstance(latest_user, list):
            latest_user = json.dumps(latest_user)
        shapes.append(
            {
                "stream": request.get("stream"),
                "message_roles": [message.get("role") for message in request.get("messages", [])],
                "tool_names": [tool.get("function", {}).get("name") for tool in tools],
                "write_required": write.get("parameters", {}).get("required", []),
                "write_properties": sorted(write.get("parameters", {}).get("properties", {}).keys()),
                "latest_user_excerpt": str(latest_user)[-2_000:],
            }
        )
    return shapes


def event_types(output: str) -> list[str]:
    types = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        item_type = item.get("type")
        if isinstance(item_type, str):
            types.append(item_type)
    return types


def checkpoint_request_count(requests: list[dict[str, Any]]) -> int:
    serialized = (json.dumps(request.get("messages", []), ensure_ascii=False) for request in requests)
    return sum("<conversation-checkpoint>" in messages for messages in serialized)


def write_confirmation_gate(workdir: Path) -> tuple[Path, Path, Path, Path]:
    """Create a non-elevated program that blocks until the test releases it."""
    gate = workdir / "confirmation_gate.py"
    waiting = workdir / "confirmation-waiting.marker"
    approval = workdir / "confirmation-approved.marker"
    result = workdir / "confirmation-result.txt"
    gate.write_text(
        """from pathlib import Path
import sys
import time

waiting, approval, result = (Path(value) for value in sys.argv[1:4])
waiting.write_text("waiting\\n", encoding="utf-8")
deadline = time.monotonic() + 10
while not approval.exists() and time.monotonic() < deadline:
    time.sleep(0.05)
if not approval.exists():
    raise SystemExit("confirmation timed out")
result.write_text("approved\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    return gate, waiting, approval, result


def powershell_call(*paths: Path) -> str:
    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    return "& " + " ".join(quote(str(path)) for path in paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-artifacts", action="store_true", help="print and retain the temporary fixture directory")
    parser.add_argument("--context", type=int, default=CONTEXT_LIMIT, help="declared fixture context (at least 4096)")
    args = parser.parse_args()
    try:
        configure_context(args.context)
    except ValueError as error:
        parser.error(str(error))
    executable = shutil.which("opencode")
    if not executable:
        print("NOT_RUN: opencode executable was not found on PATH.", file=sys.stderr)
        return 2

    server = FakeOpenAiServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    temp = tempfile.TemporaryDirectory(prefix="opencode-262k-workflow-")
    root = Path(temp.name)
    try:
        workdir = root / "project"
        workdir.mkdir()
        write_config(workdir, f"http://127.0.0.1:{server.server_port}/v1")
        session = "ses_opencode_262k_workflow"
        try:
            initial = run_opencode(
                [
                    executable,
                    "--print-logs",
                    "--log-level",
                    "debug",
                    "run",
                "--standalone",
                "--auto",
                "--format",
                "json",
                "--model",
                f"fixture/{MODEL_ID}",
                "--agent",
                "build",
                "--session",
                session,
                "Create workflow.txt with the initial workflow text.",
                ],
                workdir,
                root,
            )
        except subprocess.TimeoutExpired as error:
            with server.lock:
                paths = list(server.paths)
            raise RuntimeError(f"OpenCode exceeded the isolated 25-second limit; endpoint paths={paths!r}.") from error
        if initial.returncode != 0:
            print(initial.stdout, end="")
            print(initial.stderr, end="", file=sys.stderr)
            return initial.returncode
        follow_up = run_opencode(
            [
                executable,
                "--print-logs",
                "run",
                "--standalone",
                "--auto",
                "--format",
                "json",
                "--model",
                f"fixture/{MODEL_ID}",
                "--agent",
                "build",
                "--session",
                session,
                "REVISE_WORKFLOW: replace workflow.txt with the revised workflow text.",
            ],
            workdir,
            root,
        )
        if follow_up.returncode != 0:
            with server.lock:
                shapes = request_shapes(server.requests)
            raise RuntimeError(
                f"Follow-up exited with {follow_up.returncode}; request shapes={shapes!r}; "
                f"stderr tail={follow_up.stderr[-1000:]!r}."
            )
        gate, waiting, approval, confirmation_result = write_confirmation_gate(workdir)
        server.confirmation_command = powershell_call(Path(sys.executable), gate, waiting, approval, confirmation_result)
        release_observed = threading.Event()

        def release_confirmation() -> None:
            deadline = time.monotonic() + 10
            while not waiting.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            if waiting.exists():
                time.sleep(2)
                approval.write_text("approved by fixture\n", encoding="utf-8")
                release_observed.set()

        release_thread = threading.Thread(target=release_confirmation, daemon=True)
        release_thread.start()
        started = time.monotonic()
        confirmation = run_opencode(
            [
                executable,
                "--print-logs",
                "run",
                "--standalone",
                "--auto",
                "--format",
                "json",
                "--model",
                f"fixture/{MODEL_ID}",
                "--agent",
                "build",
                "--session",
                "ses_opencode_confirmation_resume",
                "WAIT_FOR_CONFIRMATION: run the isolated confirmation program, then create the follow-up file.",
            ],
            workdir,
            root,
        )
        elapsed = time.monotonic() - started
        release_thread.join(timeout=2)
        if confirmation.returncode != 0:
            with server.lock:
                shapes = request_shapes(server.requests)
            raise RuntimeError(
                f"Confirmation flow exited with {confirmation.returncode}; request shapes={shapes!r}; "
                f"stderr tail={confirmation.stderr[-1000:]!r}."
            )
        continued = workdir / "confirmation-follow-up.txt"
        if not release_observed.is_set() or confirmation_result.read_text(encoding="utf-8") != "approved\n":
            raise RuntimeError("The isolated confirmation program was not released by the delayed approval fixture.")
        if continued.read_text(encoding="utf-8") != "continued after confirmation\n":
            raise RuntimeError("OpenCode did not execute the action following delayed confirmation.")
        if elapsed < 1.5:
            raise RuntimeError(f"Confirmation flow finished too early to observe the delayed approval: {elapsed:.3f}s.")
        with server.lock:
            request_count = len(server.requests)
            paths = list(server.paths)
            shapes = request_shapes(server.requests)
            checkpoints = checkpoint_request_count(server.requests)
        expected = "revised by follow-up\n"
        actual = (workdir / "workflow.txt").read_text(encoding="utf-8") if (workdir / "workflow.txt").is_file() else None
        if actual != expected:
            raise RuntimeError(f"Expected follow-up edit {expected!r}, received {actual!r}; request shapes={shapes!r}.")
        if request_count < 6:
            raise RuntimeError(f"Expected title, tool, and final requests for two turns; received {request_count}; request shapes={shapes!r}.")
        follow_up_events = event_types(follow_up.stdout)
        if checkpoints < 1:
            raise RuntimeError(
                "OpenCode did not send a compacted conversation checkpoint before the follow-up; "
                f"events={follow_up_events!r}; request shapes={shapes!r}."
            )
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "model_context": CONTEXT_LIMIT,
                    "compaction": {
                        "auto": True,
                        "keep": COMPACTION_KEEP,
                        "buffer": COMPACTION_BUFFER,
                        "trigger": COMPACTION_TRIGGER,
                    },
                    "model_requests": request_count,
                    "compacted_checkpoint_requests": checkpoints,
                    "endpoint_paths": paths,
                    "workflow_file": actual,
                    "confirmation_delay_seconds": round(elapsed, 3),
                    "confirmation_file": continued.read_text(encoding="utf-8"),
                    "initial_event_types": event_types(initial.stdout),
                    "follow_up_event_types": follow_up_events,
                    "confirmation_event_types": event_types(confirmation.stdout),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if args.keep_artifacts:
            print(f"Artifacts retained: {root}", file=sys.stderr)
            temp.cleanup = lambda: None  # type: ignore[method-assign]
        else:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
