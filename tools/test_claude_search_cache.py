"""Public-search single-flight behavior under concurrency, errors and cancellation."""
from concurrent.futures import Future, ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

from tools.claude_mcp.search_cache import SearchCache, SearchCacheCancelled
from tools.claude_mcp.web_search_router import _validate


class SearchCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = SearchCache()
        self.args = _validate({'query':'Python official documentation'})

    def test_completed_provider_timeout_is_propagated_instead_of_waited_forever(self):
        future = Future()
        future.set_exception(TimeoutError('provider timed out'))
        self.cache._inflight[self.cache._key(self.args)] = future
        # A daemon isolates the regression so a failed test cannot hang the suite.
        errors = []
        def wait():
            try:
                self.cache.get_or_compute(self.args, lambda: self.fail('duplicate provider call'))
            except Exception as exc:
                errors.append(exc)
        waiter = threading.Thread(target=wait, daemon=True)
        waiter.start()
        waiter.join(timeout=1)
        self.assertFalse(waiter.is_alive(), 'completed provider TimeoutError was swallowed')
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], TimeoutError)

    def test_concurrent_identical_searches_execute_provider_once(self):
        start = threading.Barrier(8)
        calls = []
        def produce():
            calls.append(1)
            return {'results':[{'url':'https://python.org'}]}
        def search(_index):
            start.wait(timeout=2)
            return self.cache.get_or_compute(self.args, produce)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(search, range(8)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 8)
        results[0]['results'][0]['url'] = 'changed'
        cached = self.cache.get_or_compute(self.args, lambda: self.fail('cached query dispatched'))
        self.assertEqual(cached['results'][0]['url'], 'https://python.org')

    def test_cancelling_duplicate_waiter_does_not_cancel_shared_request(self):
        future = Future()
        self.cache._inflight[self.cache._key(self.args)] = future
        cancellation = threading.Event()
        entered = threading.Event()
        original = future.result
        def result(*args, **kwargs):
            entered.set()
            return original(*args, **kwargs)
        errors = []
        def wait():
            try:
                self.cache.get_or_compute(self.args, lambda: None, cancellation)
            except Exception as exc:
                errors.append(exc)
        with patch.object(future, 'result', side_effect=result):
            waiter = threading.Thread(target=wait, daemon=True)
            waiter.start()
            self.assertTrue(entered.wait(1))
            cancellation.set()
            waiter.join(timeout=1)
        self.assertFalse(waiter.is_alive())
        self.assertIsInstance(errors[0], SearchCacheCancelled)
        self.assertFalse(future.cancelled())
        self.assertFalse(future.done())

    def test_freshness_and_index_generation_do_not_reuse_stale_search(self):
        calls = []
        def produce():
            calls.append(1)
            return {'results':[]}
        self.cache.get_or_compute(self.args, produce, namespace='index-before')
        self.cache.get_or_compute(self.args, produce, namespace='index-after')
        fresh = _validate({'query':self.args['query'], 'time_range':'day'})
        self.cache.get_or_compute(fresh, produce, namespace='index-after')
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.cache._ttl(fresh), SearchCache.FRESH_TTL_SECONDS)


if __name__ == '__main__':
    unittest.main()
