"""Transport/scaling regressions; no real GUI, network, or REA analysis."""
import json
from io import StringIO
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.claude_mcp import lazy_dispatcher as lazy


CHILD = r'''import json, sys
mode = sys.argv[1]
version = 0
for line in sys.stdin:
    r = json.loads(line)
    if r.get('id') is None: continue
    m = r.get('method')
    if m == 'initialize':
        if mode == 'slow_init':
            import time
            time.sleep(1)
        result = {'protocolVersion':'2025-06-18'}
    elif m == 'tools/list':
        if mode == 'changing_list':
            print(json.dumps({'jsonrpc':'2.0','method':'notifications/tools/list_changed'}), flush=True)
        count = 800 if mode == 'large_list' else 1
        result = {'tools':[{'name':'image_'+str(version)+'_'+str(i),
            'description':'Inspect screenshot ' * (50 if count > 1 else 1),
            'inputSchema':{'type':'object'}} for i in range(count)]}
    elif m == 'tools/call':
        if mode == 'invalid_call_result':
            from pathlib import Path
            with Path(sys.argv[2]).open('a', encoding='utf-8') as stream:
                stream.write('executed\n')
            print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':[]}), flush=True)
            continue
        if mode == 'oversize':
            sys.stdout.write('A' * 2049)
            sys.stdout.flush()
            continue
        if mode == 'storm':
            for i in range(10000):
                print(json.dumps({'jsonrpc':'2.0','method':'notifications/progress','params':{'progress':i}}))
        if mode == 'changing':
            version += 1
            print(json.dumps({'jsonrpc':'2.0','method':'notifications/tools/list_changed'}), flush=True)
        result = {'content':[{'type':'image','mimeType':'image/png','data':'A' * (1048576 if mode == 'image' else 4)}],
                  'structuredContent':{'preserved':True}}
    else: result = {}
    print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}), flush=True)
'''


class DispatcherBoundsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.child = Path(temp.name)/'child.py'
        self.child.write_text(CHILD, encoding='utf-8')

    def server(self, mode):
        server = lazy.ChildServer('cua-driver', [sys.executable, str(self.child), mode])
        self.addCleanup(server.close)
        return server

    def test_large_image_result_preserved_without_schema_size_limit(self):
        server = self.server('image')
        name = lazy.search_catalog(server, 'image')[0]['name']
        result = server.call(name, {})
        self.assertEqual(result['content'][0]['data'], 'A'*1048576)
        self.assertEqual(result['structuredContent'], {'preserved':True})

    def test_executed_call_with_invalid_result_is_not_dispatched_again(self):
        server = self.server('invalid_call_result')
        counter = self.child.parent/'executions.txt'
        server.command.append(str(counter))
        name = lazy.search_catalog(server, 'image')[0]['name']
        with self.assertRaisesRegex(lazy.DispatcherError, 'invalid response'):
            server.call(name, {})
        with self.assertRaisesRegex(lazy.DispatcherError, 'was interrupted'):
            server.call(name, {})
        self.assertEqual(counter.read_text(encoding='utf-8').splitlines(), ['executed'])

    def test_failed_flush_after_write_quarantines_uncertain_call(self):
        writes = []
        class FailedFlush:
            def write(self, value):
                writes.append(value)
            def flush(self):
                raise OSError('fixture lost delivery acknowledgement')
        server = lazy.ChildServer('cua-driver', ['fixture-no-process-started'])
        server.process = SimpleNamespace(stdin=FailedFlush(), poll=lambda: None)
        server.discovered.add('run')
        with self.assertRaisesRegex(lazy.DispatcherError, 'input closed'):
            server.call('run', {})
        with self.assertRaisesRegex(lazy.DispatcherError, 'was interrupted'):
            server.call('run', {})
        self.assertEqual(len(writes), 1)

    def test_invalid_call_ids_never_dispatch_synchronously(self):
        executed = []
        child = SimpleNamespace(call=lambda *_args: executed.append(True) or {})
        dispatcher = lazy.Dispatcher({'cua-driver':child})
        for rid in ([], {}, None, True, 1.5):
            with self.subTest(rid=rid):
                response = dispatcher.handle({'jsonrpc':'2.0','id':rid,'method':'tools/call',
                    'params':{'name':'call_tool','arguments':{'server':'cua-driver','name':'run','arguments':{}}}})
                self.assertIsNotNone(response)
                self.assertEqual(response.get('error',{}).get('code'), -32600)
        self.assertEqual(executed, [])

    def test_falsey_nonobject_params_and_arguments_are_rejected(self):
        dispatcher = lazy.Dispatcher({})
        for value in (False, 0, '', []):
            with self.subTest(params=value):
                response = dispatcher.handle({'jsonrpc':'2.0','id':1,'method':'ping','params':value})
                self.assertEqual(response.get('error',{}).get('code'), -32602)
            with self.subTest(arguments=value):
                response = dispatcher.handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
                    'params':{'name':'call_tool','arguments':value}})
                self.assertEqual(response.get('error',{}).get('code'), -32602)

    def test_only_valid_cancel_notification_can_cancel_numeric_request(self):
        dispatcher = lazy.Dispatcher({})
        entered = threading.Event()
        state = {}
        observations = []
        original = dispatcher.handle
        def handle(message, cancellation=None):
            if message.get('method') != 'tools/call':
                return original(message, cancellation)
            state['event'] = cancellation
            entered.set()
            cancellation.wait(2)
            return dispatcher.response(message['id'], {})
        def inputs():
            yield json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call'})
            self.assertTrue(entered.wait(1))
            for notification in (
                {'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':True}},
                {'jsonrpc':'invalid','method':'notifications/cancelled','params':{'requestId':1}},
                {'jsonrpc':'2.0','id':99,'method':'notifications/cancelled','params':{'requestId':1}},
            ):
                yield json.dumps(notification)
                observations.append(state['event'].is_set())
            yield json.dumps({'jsonrpc':'2.0','id':2,'method':'ping'})
            yield json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':1}})
            observations.append(state['event'].is_set())
        output = StringIO()
        with patch.object(dispatcher, 'handle', side_effect=handle):
            dispatcher.serve(inputs(), output)
        self.assertEqual(observations, [False,False,False,True])
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertIn({'jsonrpc':'2.0','id':2,'result':{}}, messages)

    def test_catalog_page_larger_than_one_schema_is_supported(self):
        server = self.server('large_list')
        self.assertEqual(len(server.tools()), 800)

    def test_aggregate_catalog_bytes_are_bounded(self):
        server = self.server('large_list')
        with patch.object(lazy, 'MAX_CATALOG_BYTES', 2048):
            with self.assertRaisesRegex(lazy.DispatcherError, 'catalog exceeded the byte limit'):
                server.tools()
        self.assertIsNone(server.catalog)

    def test_oversize_unterminated_response_fails_promptly_and_quarantines_call(self):
        server = self.server('oversize')
        with patch.object(lazy, 'MAX_RPC_BYTES', 2048):
            name = lazy.search_catalog(server, 'image')[0]['name']
            start = time.monotonic()
            with self.assertRaisesRegex(lazy.DispatcherError, 'size limit.*verify before retrying'):
                server.call(name, {})
            self.assertLess(time.monotonic()-start, 2)
        self.assertTrue(server.interrupted)

    def test_notification_storm_does_not_fill_response_queue(self):
        server = self.server('storm')
        name = lazy.search_catalog(server, 'image')[0]['name']
        self.assertEqual(server.call(name, {})['structuredContent'], {'preserved':True})
        self.assertLessEqual(server.responses.qsize(), 1)
        self.assertIsNone(server.read_error)

    def test_invalid_child_cannot_grow_response_queue(self):
        server = self.server('image')
        stream = StringIO(''.join(json.dumps({'id':i,'result':{}})+'\n' for i in range(100)))
        server.process = SimpleNamespace(stdout=stream)
        try:
            server._read_stdout()
            self.assertEqual(server.responses.qsize(), lazy.MAX_QUEUED_RESPONSES)
            self.assertIn('overflowed', server.read_error)
            self.assertTrue(server.reader_done.is_set())
        finally:
            server.process = None

    def test_list_change_invalidates_discovery_and_refreshes_only_on_search(self):
        server = self.server('changing')
        old = lazy.search_catalog(server, 'image')[0]['name']
        server.call(old, {})  # returns only after the preceding list_changed was read
        self.assertIsNone(server.catalog)
        self.assertEqual(server.search_index, [])
        with self.assertRaisesRegex(lazy.DispatcherError, 'search_tools'):
            server.call(old, {})
        new = lazy.search_catalog(server, 'image')[0]['name']
        self.assertNotEqual(old, new)
        self.assertNotIn(old, server.discovered)

    def test_list_changes_during_discovery_do_not_publish_stale_catalog(self):
        server = self.server('changing_list')
        with self.assertRaisesRegex(lazy.DispatcherError, 'changed during discovery'):
            server.tools()
        self.assertIsNone(server.catalog)

    def test_top_k_matches_original_ranking_with_ties_and_korean_aliases(self):
        server = self.server('image')
        catalog = {name:{'name':name, 'description':description} for name, description in [
            ('x_window', 'List windows'), ('a_window', 'Click screenshot'),
            ('click', 'Click'), ('z_window', None), ('only_description', 'window list windows')]}
        server.catalog = catalog
        server.search_index = server._prepare_search_index(catalog)
        with patch.object(server, '_start'):
            result = lazy.search_catalog(server, '창 목록', 3)
        # Aliases add window, list, windows. Exact query is not a literal name.
        self.assertEqual([r['name'] for r in result], ['x_window', 'a_window', 'only_description'])

    def test_busy_child_does_not_wait_for_full_tool_timeout_or_dispatch_again(self):
        server = self.server('image')
        server.lock.acquire()
        try:
            with patch.object(lazy, 'CHILD_QUEUE_TIMEOUT_SECONDS', 0.01):
                with self.assertRaisesRegex(lazy.DispatcherError, 'not dispatched'):
                    server.call('image_0_0', {})
            self.assertIsNone(server.process)
        finally:
            server.lock.release()

    def test_pre_cancelled_discovery_never_launches_child(self):
        server = self.server('image')
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(lazy.DispatcherError, 'cancelled before dispatch'):
            server.tools(cancel)
        self.assertIsNone(server.process)

    def test_cancel_during_initialization_does_not_wait_for_startup_timeout(self):
        server = self.server('slow_init')
        cancel = threading.Event()
        timer = threading.Timer(0.1, cancel.set)
        timer.start()
        self.addCleanup(timer.join)
        start = time.monotonic()
        with self.assertRaisesRegex(lazy.DispatcherError, 'cancelled'):
            server.tools(cancel)
        self.assertLess(time.monotonic()-start, 0.8)
        self.assertTrue(server.interrupted)

    def test_parallel_admission_bounds_workers_and_keeps_ping_and_cancel_responsive(self):
        dispatcher = lazy.Dispatcher({})
        entered = [threading.Event(), threading.Event()]
        cancelled = []
        seen = []
        original = dispatcher.handle

        def handle(message, cancellation=None):
            if message.get('method') != 'tools/call':
                return original(message, cancellation)
            rid = message['id']
            seen.append(rid)
            entered[rid].set()
            cancellation.wait(2)
            cancelled.append((rid, cancellation.is_set()))
            return dispatcher.response(rid, {})

        def inputs():
            for rid in (0, 1):
                yield json.dumps({'jsonrpc':'2.0','id':rid,'method':'tools/call'})
                self.assertTrue(entered[rid].wait(1))
            yield json.dumps({'jsonrpc':'2.0','id':0,'method':'tools/call'})
            yield json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call'})
            yield json.dumps({'jsonrpc':'2.0','id':3,'method':'ping'})
            yield json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':0}})

        output = StringIO()
        with patch.object(lazy, 'MAX_ACTIVE_CALLS', 2), patch.object(dispatcher, 'handle', side_effect=handle):
            dispatcher.serve(inputs(), output)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(sorted(seen), [0,1])
        self.assertIn((0,True), cancelled)
        self.assertTrue(any(m.get('id') == 0 and 'duplicate active' in m.get('error',{}).get('message','') for m in messages))
        self.assertTrue(any(m.get('id') == 2 and 'not dispatched' in m.get('error',{}).get('message','') for m in messages))
        self.assertIn({'jsonrpc':'2.0','id':3,'result':{}}, messages)


if __name__ == '__main__':
    unittest.main()
