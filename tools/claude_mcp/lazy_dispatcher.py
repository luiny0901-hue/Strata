"""On-demand access to configured CUA/REA MCP servers and optional public web search.

The parent exposes two small tools. A child MCP server is started only when
search_tools selects it; tools/call accepts names returned by that search.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import claude_mcp_config as mcp_config  # noqa: E402
from tools.claude_mcp import exa_search  # noqa: E402
from tools.claude_mcp import searxng_search  # noqa: E402
from tools.claude_mcp import web_search_router  # noqa: E402

PROTOCOL = "2025-06-18"
MAX_CATALOG_TOOLS = 4096
MAX_TOOL_BYTES = 512 * 1024
MAX_SEARCH_RESULTS = 8
CATALOG_PAGE_TIMEOUT_SECONDS = 30
CATALOG_TOTAL_TIMEOUT_SECONDS = 90
QUERY_ALIASES = {
    "창": "window", "창목록": "window list windows", "화면": "screen screenshot display window",
    "스크린샷": "screenshot", "캡처": "capture screenshot", "클릭": "click",
    "누르기": "click press", "키보드": "keyboard key type", "단축키": "hotkey shortcut",
    "마우스": "mouse cursor pointer", "커서": "cursor pointer", "이동": "move",
    "역분석": "reverse engineering decompile disassemble", "디컴파일": "decompile",
    "바이너리": "binary executable", "실행파일": "executable binary",
    "프로그램": "application program", "앱": "application app", "문자열": "string",
    "함수": "function", "클래스": "class", "리소스": "resource",
}

TOOL_DEFS = [
    {
        "name": "search_tools",
        "description": (
            "Search the on-demand CUA or REA MCP catalog before calling a tool. "
            "Choose cua-driver only for GUI observation or interaction; choose rea only for "
            "reverse engineering a built program or application. Ordinary source-code reading "
            "uses native file tools. Returns a few matching tools and their exact input schemas."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "server": {"type": "string", "enum": ["cua-driver", "rea"]},
                "query": {"type": "string", "minLength": 2, "maxLength": 200},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
            },
            "required": ["server", "query"],
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "call_tool",
        "description": (
            "Call one exact CUA or REA tool returned by search_tools in this session. "
            "Use its returned input schema and pass arguments unchanged. Do not retry a call "
            "whose outcome is ambiguous; inspect its result first."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "server": {"type": "string", "enum": ["cua-driver", "rea"]},
                "name": {"type": "string", "minLength": 1, "maxLength": 160},
                "arguments": {"type": "object"},
            },
            "required": ["server", "name", "arguments"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
]

class DispatcherError(RuntimeError):
    pass


class ChildServer:
    """One serialized JSON-RPC connection to a lazily started stdio MCP child."""

    def __init__(self, name: str, command: list[str], env: dict[str, str] | None = None):
        if name not in ("cua-driver", "rea") or not command or not all(isinstance(x, str) for x in command):
            raise DispatcherError("invalid configured MCP server")
        self.name = name
        self.command = command
        self.env = env or {}
        self.process: subprocess.Popen | None = None
        self.responses: queue.Queue[str | None] = queue.Queue()
        self.reader: threading.Thread | None = None
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.request_id = 0
        self.protocol = PROTOCOL
        self.catalog: dict[str, dict] | None = None
        self.discovered: set[str] = set()
        self.interrupted = False

    def _start(self):
        if self.interrupted:
            raise DispatcherError(f"{self.name} was interrupted; inspect the operation before starting a new session")
        if self.process is not None:
            if self.process.poll() is None:
                return
            raise DispatcherError(f"{self.name} MCP process exited")
        child_env = os.environ.copy()
        child_env.update(self.env)
        try:
            self.process = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                bufsize=1, env=child_env,
            )
        except OSError as exc:
            raise DispatcherError(f"could not start {self.name} MCP server") from exc
        self.reader = threading.Thread(target=self._read_stdout, name=f"{self.name}-mcp-reader", daemon=True)
        self.reader.start()
        initialized = self._request("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "strata-agent-tools", "version": "1.0.0"},
        }, timeout=15)
        server_protocol = initialized.get("protocolVersion")
        if isinstance(server_protocol, str):
            self.protocol = server_protocol
        self._notify("notifications/initialized", {})

    def _read_stdout(self):
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.responses.put(line)
        finally:
            self.responses.put(None)

    def _notify(self, method: str, params: dict):
        assert self.process is not None and self.process.stdin is not None
        with self.write_lock:
            self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
            self.process.stdin.flush()

    def _request(self, method: str, params: dict, *, timeout: float, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise DispatcherError("request cancelled before dispatch")
        self.request_id += 1
        rid = self.request_id
        assert self.process is not None and self.process.stdin is not None
        request = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            with self.write_lock:
                self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise DispatcherError(f"{self.name} MCP input closed") from exc
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                self.interrupted = True
                self._notify("notifications/cancelled", {"requestId": rid, "reason": "parent MCP request cancelled"})
                raise DispatcherError("request cancelled; the underlying operation may still have completed")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if method == "tools/call":
                    self.interrupted = True
                    self._notify("notifications/cancelled", {"requestId": rid, "reason": "dispatcher timeout"})
                    raise DispatcherError(
                        f"{self.name} tool call timed out; the operation may have completed; verify before retrying")
                raise DispatcherError(f"{self.name} MCP {method} timed out")
            try:
                line = self.responses.get(timeout=min(0.1, remaining) if cancel_event is not None else remaining)
            except queue.Empty as exc:
                if remaining <= 0:
                    if method == "tools/call":
                        self.interrupted = True
                        self._notify("notifications/cancelled", {"requestId": rid, "reason": "dispatcher timeout"})
                        raise DispatcherError(
                            f"{self.name} tool call timed out; the operation may have completed; verify before retrying") from exc
                    raise DispatcherError(f"{self.name} MCP {method} timed out") from exc
                continue
            if line is None:
                if method == "tools/call":
                    self.interrupted = True
                    raise DispatcherError(
                        f"{self.name} tool call connection closed; the operation may have completed; verify before retrying")
                raise DispatcherError(f"{self.name} MCP process closed its output")
            if len(line.encode("utf-8", "replace")) > MAX_TOOL_BYTES:
                raise DispatcherError(f"{self.name} MCP response exceeded the size limit")
            try:
                message = json.loads(line)
            except ValueError:
                continue  # tolerate non-JSON diagnostics without forwarding them
            if not isinstance(message, dict) or message.get("id") != rid:
                continue  # notifications and unrelated responses are not tool results
            if "error" in message:
                error = message.get("error")
                reason = error.get("message") if isinstance(error, dict) else "MCP request failed"
                raise DispatcherError(f"{self.name} MCP request failed: {str(reason)[:300]}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise DispatcherError(f"{self.name} MCP returned an invalid response")
            return result

    def _acquire(self, cancel_event):
        while not self.lock.acquire(timeout=0.1):
            if cancel_event is not None and cancel_event.is_set():
                raise DispatcherError("request cancelled while waiting for the MCP server")

    def tools(self, cancel_event=None):
        self._acquire(cancel_event)
        try:
            self._start()
            if self.catalog is not None:
                return self.catalog
            catalog: dict[str, dict] = {}
            cursor = None
            seen_cursors: set[str] = set()
            deadline = time.monotonic() + CATALOG_TOTAL_TIMEOUT_SECONDS
            for _ in range(100):
                if cancel_event is not None and cancel_event.is_set():
                    raise DispatcherError("request cancelled while discovering the MCP tool catalog")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DispatcherError(f"{self.name} MCP tool catalog discovery timed out")
                params = {"cursor": cursor} if cursor is not None else {}
                result = self._request(
                    "tools/list", params,
                    timeout=min(CATALOG_PAGE_TIMEOUT_SECONDS, remaining),
                    cancel_event=cancel_event,
                )
                rows = result.get("tools", [])
                if not isinstance(rows, list):
                    raise DispatcherError(f"{self.name} MCP returned an invalid tool list")
                for tool in rows:
                    if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                        continue
                    encoded = json.dumps(tool, ensure_ascii=False).encode("utf-8")
                    if len(encoded) > MAX_TOOL_BYTES:
                        continue
                    catalog[tool["name"]] = tool
                    if len(catalog) > MAX_CATALOG_TOOLS:
                        raise DispatcherError(f"{self.name} MCP catalog exceeded the tool limit")
                next_cursor = result.get("nextCursor")
                if next_cursor is None:
                    break
                if not isinstance(next_cursor, str) or not next_cursor:
                    raise DispatcherError(f"{self.name} MCP returned an invalid tool-list cursor")
                if next_cursor in seen_cursors:
                    raise DispatcherError(f"{self.name} MCP repeated a tool-list cursor")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
            else:
                raise DispatcherError(f"{self.name} MCP pagination exceeded the page limit")
            self.catalog = catalog
            return catalog
        finally:
            self.lock.release()

    def call(self, name: str, arguments: dict, cancel_event=None):
        self._acquire(cancel_event)
        try:
            if name not in self.discovered:
                raise DispatcherError("search_tools must return this tool before it can be called")
            self._start()
            return self._request("tools/call", {"name": name, "arguments": arguments}, timeout=600,
                                 cancel_event=cancel_event)
        finally:
            self.lock.release()

    def close(self):
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for stream in (process.stdin, process.stdout):
            if stream and not stream.closed:
                stream.close()
        if self.reader and self.reader.is_alive():
            self.reader.join(timeout=1)


def configured_servers(config_path: Path) -> dict[str, ChildServer]:
    projected = mcp_config.read(config_path).get("mcpServers", {})
    result = {}
    for name in ("cua-driver", "rea"):
        row = projected.get(name)
        if not isinstance(row, dict):
            continue
        command = [row.get("command"), *row.get("args", [])]
        if not isinstance(command[0], str) or not all(isinstance(part, str) for part in command):
            raise DispatcherError(f"invalid source configuration for {name}")
        env = row.get("env", {})
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise DispatcherError(f"invalid environment configuration for {name}")
        result[name] = ChildServer(name, command, env)
    if not result:
        raise DispatcherError("Claude MCP config has no enabled local CUA or REA server")
    return result


def _words(value: str) -> list[str]:
    return [word for word in re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE) if len(word) > 1]


def search_catalog(server: ChildServer, query: str, limit: int = 5, cancel_event=None) -> list[dict]:
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
        raise DispatcherError("query must contain 2 to 200 characters")
    if type(limit) is not int or not 1 <= limit <= MAX_SEARCH_RESULTS:
        raise DispatcherError(f"limit must be between 1 and {MAX_SEARCH_RESULTS}")
    catalog = server.tools(cancel_event)
    terms = _words(query)
    compact_query = re.sub(r"\s+", "", query.casefold())
    for korean, english in QUERY_ALIASES.items():
        if korean in compact_query:
            terms.extend(_words(english))
    terms = list(dict.fromkeys(terms))
    needle = query.casefold().strip()
    ranked = []
    for name, tool in catalog.items():
        description = tool.get("description", "")
        if not isinstance(description, str):
            description = ""
        name_text = name.casefold()
        description_text = description.casefold()
        searchable = name_text + " " + description_text
        score = sum(3 for word in terms if word in name_text) + sum(1 for word in terms if word in description_text)
        if needle in name_text:
            score += 8
        elif needle in description_text:
            score += 3
        if score:
            ranked.append((score, name, tool))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    results = [tool for _score, _name, tool in ranked[:limit]]
    server.discovered.update(tool["name"] for tool in results)
    return results


class Dispatcher:
    def __init__(self, servers: dict[str, ChildServer], exa_api_key: str | None = None,
                 tavily_api_key: str | None = None, searxng_url: str | None = None):
        self.servers = servers
        self.search_router = web_search_router.WebSearchRouter(
            exa_api_key=exa_api_key, tavily_api_key=tavily_api_key, searxng_url=searxng_url,
        )

    def tool_definitions(self) -> list[dict]:
        tools = list(TOOL_DEFS)
        if self.search_router.available:
            tools.append(web_search_router.WEB_SEARCH_TOOL_DEF)
        return tools

    @staticmethod
    def response(rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def error(rid, code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}

    @staticmethod
    def failure(message):
        return {"content": [{"type": "text", "text": message}], "isError": True}

    def handle(self, message, cancel_event=None):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return self.error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request")
        rid = message.get("id")
        if rid is None:
            return None
        method = message["method"]
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return self.error(rid, -32602, "params must be an object")
        if method == "initialize":
            version = params.get("protocolVersion")
            protocol = version if isinstance(version, str) else PROTOCOL
            return self.response(rid, {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "strata-agent-tools", "version": "1.0.0"},
                "instructions": (
                    "Use CUA only for requested GUI observation or interaction, and REA only for reverse engineering "
                    "existing built applications. For current public information, use web_search when available; "
                    "never include private code, logs, credentials, or personal data in search queries. "
                    "First search the selected CUA/REA catalog narrowly and call only a returned tool with its exact schema."
                ),
            })
        if method == "ping":
            return self.response(rid, {})
        if method == "tools/list":
            return self.response(rid, {"tools": self.tool_definitions()})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                return self.error(rid, -32602, "arguments must be an object")
            try:
                if name == "search_tools":
                    selected = args.get("server")
                    if selected not in self.servers:
                        raise DispatcherError("select one configured server: cua-driver or rea")
                    hits = search_catalog(self.servers[selected], args.get("query"), args.get("limit", 5), cancel_event)
                    return self.response(rid, {"content": [{"type": "text", "text": json.dumps(
                        {"server": selected, "count": len(hits), "tools": hits}, ensure_ascii=False,
                    )}], "isError": False})
                if name == "call_tool":
                    selected, tool_name = args.get("server"), args.get("name")
                    tool_args = args.get("arguments")
                    if selected not in self.servers or not isinstance(tool_name, str) or not isinstance(tool_args, dict):
                        raise DispatcherError("server, discovered tool name, and object arguments are required")
                    return self.response(rid, self.servers[selected].call(tool_name, tool_args, cancel_event))
                if name == "web_search":
                    result = self.search_router.search(args, cancel_event)
                    return self.response(rid, {"content": [{"type": "text", "text": json.dumps(
                        result, ensure_ascii=False,
                    )}], "isError": False})
                return self.error(rid, -32602, "unknown dispatcher tool")
            except web_search_router.WebSearchError as exc:
                return self.response(rid, self.failure(str(exc)))
            except searxng_search.SearXNGSearchError as exc:
                return self.response(rid, self.failure(str(exc)))
            except DispatcherError as exc:
                return self.response(rid, self.failure(str(exc)))
            except Exception:
                return self.response(rid, self.failure("dispatcher request failed"))
        if method in ("resources/list", "prompts/list"):
            key = method.split("/", 1)[0]
            return self.response(rid, {key: []})
        return self.error(rid, -32601, "method not found")

    def serve(self, inp, out):
        write_lock = threading.Lock()
        pending_lock = threading.Lock()
        pending: dict[str | int, threading.Event] = {}
        workers = []

        def send(response):
            if response is None:
                return
            with write_lock:
                out.write(json.dumps(response, ensure_ascii=False) + "\n")
                out.flush()

        def run_call(message, cancellation):
            rid = message.get("id")
            try:
                response = self.handle(message, cancellation)
                if cancellation.is_set():
                    response = self.error(rid, -32800,
                        "request cancelled; the underlying tool may still have completed; verify before retrying")
                send(response)
            finally:
                with pending_lock:
                    pending.pop(rid, None)

        for raw in inp:
            try:
                message = json.loads(raw)
            except (ValueError, TypeError):
                send(self.error(None, -32700, "parse error"))
                continue
            else:
                if (isinstance(message, dict) and message.get("method") == "notifications/cancelled"
                        and isinstance(message.get("params"), dict)):
                    request_id = message["params"].get("requestId")
                    with pending_lock:
                        cancellation = pending.get(request_id) if isinstance(request_id, (str, int)) else None
                    if cancellation is not None:
                        cancellation.set()
                    continue
                if (isinstance(message, dict) and message.get("method") == "tools/call"
                        and "id" in message and isinstance(message.get("id"), (str, int))):
                    cancellation = threading.Event()
                    with pending_lock:
                        pending[message["id"]] = cancellation
                    worker = threading.Thread(target=run_call, args=(message, cancellation), daemon=True)
                    worker.start()
                    workers.append(worker)
                    workers = [worker for worker in workers if worker.is_alive()]
                    continue
                send(self.handle(message))
        with pending_lock:
            for cancellation in pending.values():
                cancellation.set()
        for worker in workers:
            worker.join(timeout=1)
        self.close()

    def close(self):
        for server in self.servers.values():
            server.close()


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-config", type=Path)
    args = parser.parse_args(argv)
    try:
        config_path = args.mcp_config or (Path.home() / ".claude" / "strata-mcp.json")
        dispatcher = Dispatcher(
            configured_servers(config_path),
            exa_api_key=os.environ.get("EXA_API_KEY"),
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            searxng_url=os.environ.get("SEARXNG_URL"),
        )
    except (OSError, ValueError, DispatcherError, searxng_search.SearXNGSearchError) as exc:
        print(f"agent-tools: {exc}", file=sys.stderr)
        return 2
    atexit.register(dispatcher.close)
    dispatcher.serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
