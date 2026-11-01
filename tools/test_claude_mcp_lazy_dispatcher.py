import json
import sys
import tempfile
import unittest
from pathlib import Path
import threading
import time
from io import StringIO
from unittest.mock import patch

from tools.claude_mcp import lazy_dispatcher as lazy


CHILD = r'''import json, os, sys
name = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    rid = request.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": name}}
    elif method == "tools/list":
        result = {"tools": [
            {"name": name + "_list_windows", "description": "List visible windows and titles", "inputSchema": {"type": "object", "properties": {}}},
            {"name": name + "_click", "description": "Click a GUI position", "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}}}},
        ]}
    elif method == "tools/call":
        result = {"content": [{"type": "image", "data": "YQ==", "mimeType": "image/png"}, {"type": "text", "text": "ok"}], "structuredContent": {"preserved": True}, "isError": False}
    else:
        continue
    if rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
'''

SLOW_CHILD = r'''import json, os, sys, time
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    rid = request.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "slow"}}
    elif method == "tools/call":
        open(os.environ["CALL_MARKER"], "w").write("started")
        time.sleep(0.6)
        result = {"content": [{"type": "text", "text": "completed"}], "isError": False}
    elif method == "notifications/cancelled":
        open(os.environ["CANCEL_MARKER"], "w").write("cancel received")
        continue
    else:
        continue
    if rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
'''

REPEATED_CURSOR_CHILD = r'''import json, sys
for line in sys.stdin:
    request = json.loads(line)
    method, rid = request.get("method"), request.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rea"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "rea_inspect", "description": "Inspect a binary", "inputSchema": {"type": "object"}}], "nextCursor": "same"}
    else:
        continue
    if rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
'''

SLOW_LIST_CHILD = r'''import json, sys, time
for line in sys.stdin:
    request = json.loads(line)
    method, rid = request.get("method"), request.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rea"}}
    elif method == "tools/list":
        time.sleep(0.2)
        result = {"tools": []}
    else:
        continue
    if rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
'''


class LazyMcpDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        child = root / "child.py"
        child.write_text(CHILD, encoding="utf-8")
        self.cua = lazy.ChildServer("cua-driver", [sys.executable, str(child), "cua-driver"])
        self.rea = lazy.ChildServer("rea", [sys.executable, str(child), "rea"])
        self.dispatcher = lazy.Dispatcher({"cua-driver": self.cua, "rea": self.rea})
        self.addCleanup(self.dispatcher.close)

    def call(self, name, arguments, rid=1):
        return self.dispatcher.handle({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                       "params": {"name": name, "arguments": arguments}})

    def test_configured_servers_reads_claude_owned_mcp_config_not_opencode(self):
        config_path = Path(self.temp.name)/"strata-mcp.json"
        child = Path(self.temp.name)/"child.py"
        config_path.write_text(json.dumps({"mcpServers": {
            "cua-driver": {"type":"stdio","command":sys.executable,"args":[str(child),"cua-driver"],
                           "env":{"CUA_FIXTURE":"kept"}},
            "rea": {"type":"stdio","command":sys.executable,"args":[str(child),"rea"]},
            "strata-maintenance": {"type":"stdio","command":"python","args":["maintenance.py"]}}}),
            encoding="utf-8")
        servers = lazy.configured_servers(config_path)
        self.assertEqual(set(servers), {"cua-driver", "rea"})
        self.assertEqual(servers["cua-driver"].command, [sys.executable, str(child), "cua-driver"])
        self.assertEqual(servers["cua-driver"].env, {"CUA_FIXTURE":"kept"})

    def test_parent_catalog_is_small_and_does_not_start_children(self):
        response = self.dispatcher.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = response["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["search_tools", "call_tool"])
        self.assertLess(len(json.dumps(tools)), 4000)
        self.assertIsNone(self.cua.process)
        self.assertIsNone(self.rea.process)

    def test_exa_search_tool_is_hidden_without_a_key(self):
        response = self.dispatcher.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        self.assertEqual([tool["name"] for tool in response["result"]["tools"]], ["search_tools", "call_tool"])
        unavailable = self.call("web_search", {"query": "official Python release"})
        self.assertTrue(unavailable["result"]["isError"])
        self.assertIn("EXA_API_KEY", unavailable["result"]["content"][0]["text"])

    def test_exa_search_tool_is_opt_in_and_returns_results(self):
        dispatcher = lazy.Dispatcher({"cua-driver": self.cua, "rea": self.rea}, exa_api_key="test-key")
        self.addCleanup(dispatcher.close)
        tools = dispatcher.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["search_tools", "call_tool", "web_search"])
        self.assertTrue(tools[-1]["annotations"]["readOnlyHint"])
        self.assertTrue(tools[-1]["annotations"]["openWorldHint"])
        with patch.object(lazy.exa_search, "search", return_value={
            "provider": "Exa Search", "query": "official Python release", "mode": "auto",
            "results": [{"title": "Python", "url": "https://python.org", "highlights": ["Official site"]}],
        }) as search:
            response = dispatcher.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "web_search", "arguments": {
                    "query": "official Python release", "include_domains": ["python.org"],
                    "published_after": "2026-01-01",
                }}})
        self.assertFalse(response["result"]["isError"])
        result = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(result["results"][0]["url"], "https://python.org")
        search.assert_called_once_with(
            "official Python release", 5, "test-key", mode="auto",
            category=None, include_domains=["python.org"], published_after="2026-01-01", cancel_event=None,
        )

    def test_exa_search_rejects_unknown_arguments(self):
        dispatcher = lazy.Dispatcher({"cua-driver": self.cua}, exa_api_key="test-key")
        self.addCleanup(dispatcher.close)
        response = dispatcher.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "web_search", "arguments": {"query": "official Python", "api_key": "leak"}}})
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn("leak", json.dumps(response))

    def test_search_starts_only_selected_server_and_returns_input_schema(self):
        response = self.call("search_tools", {"server": "cua-driver", "query": "window", "limit": 1})
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["server"], "cua-driver")
        self.assertEqual(payload["tools"][0]["name"], "cua-driver_list_windows")
        self.assertEqual(payload["tools"][0]["inputSchema"]["type"], "object")
        self.assertIsNotNone(self.cua.process)
        self.assertIsNone(self.rea.process)
        process = self.cua.process
        self.call("search_tools", {"server": "cua-driver", "query": "click"})
        self.assertIs(self.cua.process, process)

    def test_korean_query_finds_english_catalog_entries(self):
        response = self.call("search_tools", {"server": "cua-driver", "query": "창 목록", "limit": 1})
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["tools"][0]["name"], "cua-driver_list_windows")

    def test_tool_must_be_discovered_and_child_result_is_forwarded_unchanged(self):
        denied = self.call("call_tool", {"server": "rea", "name": "rea_list_windows", "arguments": {}})
        self.assertTrue(denied["result"]["isError"])
        self.assertIsNone(self.rea.process)

        self.call("search_tools", {"server": "rea", "query": "window"})
        response = self.call("call_tool", {"server": "rea", "name": "rea_list_windows", "arguments": {"x": 1}}, rid=2)
        self.assertEqual(response["result"]["content"][0]["type"], "image")
        self.assertEqual(response["result"]["structuredContent"], {"preserved": True})
        self.assertFalse(response["result"]["isError"])

    def test_search_refuses_empty_or_unconfigured_server(self):
        invalid = self.call("search_tools", {"server": "strata-maintenance", "query": "status"})
        self.assertTrue(invalid["result"]["isError"])
        self.assertIsNone(self.cua.process)
        self.assertIsNone(self.rea.process)
        with self.assertRaises(lazy.DispatcherError):
            lazy.search_catalog(self.cua, " ")

    def test_tool_catalog_rejects_repeated_pagination_cursor(self):
        child = Path(self.temp.name) / "repeated_cursor_child.py"
        child.write_text(REPEATED_CURSOR_CHILD, encoding="utf-8")
        server = lazy.ChildServer("rea", [sys.executable, str(child)])
        self.addCleanup(server.close)
        with self.assertRaisesRegex(lazy.DispatcherError, "repeated a tool-list cursor"):
            server.tools()

    def test_tool_catalog_uses_one_total_discovery_deadline(self):
        child = Path(self.temp.name) / "slow_list_child.py"
        child.write_text(SLOW_LIST_CHILD, encoding="utf-8")
        server = lazy.ChildServer("rea", [sys.executable, str(child)])
        self.addCleanup(server.close)
        original_timeout = lazy.CATALOG_TOTAL_TIMEOUT_SECONDS
        lazy.CATALOG_TOTAL_TIMEOUT_SECONDS = 0.05
        try:
            with self.assertRaisesRegex(lazy.DispatcherError, "tools/list timed out"):
                server.tools()
        finally:
            lazy.CATALOG_TOTAL_TIMEOUT_SECONDS = original_timeout

    def test_non_discovered_tool_call_does_not_launch_server(self):
        with self.assertRaisesRegex(lazy.DispatcherError, "search_tools"):
            self.cua.call("cua-driver_click", {})
        self.assertIsNone(self.cua.process)

    def test_cancel_is_forwarded_and_uncertain_child_is_quarantined(self):
        root = Path(self.temp.name)
        child = root/'slow_child.py'
        child.write_text(SLOW_CHILD, encoding='utf-8')
        call_marker, cancel_marker = root/'call.started', root/'cancel.received'
        server = lazy.ChildServer('rea', [sys.executable, str(child)], {
            'CALL_MARKER': str(call_marker), 'CANCEL_MARKER': str(cancel_marker),
        })
        self.addCleanup(server.close)
        server.discovered.add('slow_tool')
        cancellation = threading.Event()
        errors = []

        def invoke():
            try:
                server.call('slow_tool', {}, cancellation)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=invoke)
        worker.start()
        deadline = time.monotonic()+3
        while not call_marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(call_marker.exists(), 'child tool call did not start')
        cancellation.set()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn('may still have completed', str(errors[0]))
        self.assertTrue(server.interrupted)
        deadline = time.monotonic()+2
        while not cancel_marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(cancel_marker.exists(), 'MCP cancellation notification was not forwarded')
        with self.assertRaisesRegex(lazy.DispatcherError, 'was interrupted'):
            server.call('slow_tool', {}, threading.Event())

    def test_parent_cancellation_notification_stays_responsive_during_tool_call(self):
        root = Path(self.temp.name)
        child = root/'slow_parent_child.py'
        child.write_text(SLOW_CHILD, encoding='utf-8')
        call_marker, cancel_marker = root/'parent-call.started', root/'parent-cancel.received'
        server = lazy.ChildServer('rea', [sys.executable, str(child)], {
            'CALL_MARKER': str(call_marker), 'CANCEL_MARKER': str(cancel_marker),
        })
        server.discovered.add('slow_tool')
        dispatcher = lazy.Dispatcher({'rea': server})
        self.addCleanup(dispatcher.close)
        output = StringIO()
        call = {'jsonrpc': '2.0', 'id': 17, 'method': 'tools/call', 'params': {'name': 'call_tool',
                'arguments': {'server': 'rea', 'name': 'slow_tool', 'arguments': {}}}}
        cancel = {'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 17}}

        def input_lines():
            yield json.dumps(call)
            deadline = time.monotonic()+3
            while not call_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(call_marker.exists(), 'dispatcher did not start the child request')
            yield json.dumps(cancel)
            deadline = time.monotonic()+2
            while not cancel_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)

        dispatcher.serve(input_lines(), output)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(cancel_marker.exists(), 'parent cancel notification was not forwarded')
        self.assertEqual(messages[0]['error']['code'], -32800)
        self.assertIn('verify before retrying', messages[0]['error']['message'])


if __name__ == "__main__":
    unittest.main()
