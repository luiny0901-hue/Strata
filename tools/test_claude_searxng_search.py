"""Offline contracts for SearXNG results when an engine ignores site filters."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from tools.claude_mcp import searxng_search, web_search_router


class LocalFirstRoutingTests(unittest.TestCase):
    """Local-first order: SearXNG first; free APIs spend only on failure or no results."""

    def router(self, exa=True, tavily=False):
        ledger = Mock()
        ledger.cooldown.return_value = (None, None)
        ledger.reserve_monthly.return_value = (True, 1, None)
        return web_search_router.WebSearchRouter(
            exa_api_key='exa-key' if exa else None,
            tavily_api_key='tavily-key' if tavily else None,
            searxng_url='http://127.0.0.1:8888', ledger=ledger)

    def test_local_first_queries_searxng_before_exa(self):
        router = self.router()
        with patch.dict(os.environ, {'WEB_SEARCH_ORDER': 'local'}), \
                patch.object(searxng_search, 'search',
                             return_value={'results': [{'url': 'https://a/'}], 'note': ''}) as local, \
                patch.object(web_search_router.exa_search, 'search') as exa:
            result = router._search(web_search_router._validate({'query': 'release docs'}))
        self.assertEqual(result['route'], ['Local SearXNG'])
        local.assert_called_once()
        exa.assert_not_called()
        router.ledger.reserve_monthly.assert_not_called()

    def test_zero_local_results_fall_through_to_exa_with_reason(self):
        router = self.router()
        with patch.dict(os.environ, {'WEB_SEARCH_ORDER': 'local'}), \
                patch.object(searxng_search, 'search', return_value={'results': [], 'note': ''}), \
                patch.object(web_search_router.exa_search, 'search',
                             return_value={'results': [{'title': 'x', 'url': 'https://e/'}]}):
            result = router._search(web_search_router._validate({'query': 'release docs'}))
        self.assertEqual(result['route'], ['No results in local SearXNG', 'Exa'])

    def test_local_failure_falls_through_to_exa(self):
        router = self.router()
        with patch.dict(os.environ, {'WEB_SEARCH_ORDER': 'local'}), \
                patch.object(searxng_search, 'search',
                             side_effect=searxng_search.SearXNGSearchError('engine unavailable',
                                                                           cooldown_seconds=60)), \
                patch.object(web_search_router.exa_search, 'search',
                             return_value={'results': [{'title': 'x', 'url': 'https://e/'}]}):
            result = router._search(web_search_router._validate({'query': 'release docs'}))
        self.assertEqual(result['route'], ['Local SearXNG failure', 'Exa'])
        router.ledger.set_cooldown.assert_called_once_with('searxng', 60, 'search_engine_unavailable')

    def test_api_order_keeps_exa_first(self):
        router = self.router()
        with patch.dict(os.environ, {'WEB_SEARCH_ORDER': 'api'}), \
                patch.object(searxng_search, 'search') as local, \
                patch.object(web_search_router.exa_search, 'search',
                             return_value={'results': [{'title': 'x', 'url': 'https://e/'}]}):
            result = router._search(web_search_router._validate({'query': 'release docs'}))
        self.assertEqual(result['route'], ['Exa'])
        local.assert_not_called()

    def test_zero_local_results_without_api_keys_return_empty_not_error(self):
        router = self.router(exa=False)
        with patch.dict(os.environ, {'WEB_SEARCH_ORDER': 'local'}), \
                patch.object(searxng_search, 'search', return_value={'results': [], 'note': ''}):
            result = router._search(web_search_router._validate({'query': 'release docs'}))
        self.assertEqual(result['results'], [])
        self.assertEqual(result['route'], ['Local SearXNG'])


class SearXNGDomainTests(unittest.TestCase):
    def search(self, domains):
        urls = [
            'https://python.org/downloads/',
            'https://docs.python.org/3/library/',
            'https://python.org.evil.example/downloads/',
            'https://notpython.org/downloads/',
            'https://github.com/python/cpython',
            'https://github.com/python/cpython/issues/1',
            'https://github.com/python/cpython-other',
        ]
        payload = json.dumps({'results': [{'title': 'result', 'url': url} for url in urls]}).encode()
        return searxng_search.search('release', 10, 'http://127.0.0.1:8888',
            include_domains=domains, opener=lambda *args, **kwargs: io.BytesIO(payload))['results']

    def test_domain_filter_drops_unrelated_hosts_even_when_engine_returns_them(self):
        for domain in ('python.org', '*.python.org'):
            with self.subTest(domain=domain):
                self.assertEqual([r['url'] for r in self.search([domain])], [
                    'https://python.org/downloads/', 'https://docs.python.org/3/library/'])

    def test_path_filter_has_a_segment_boundary_and_multiple_filters_are_alternatives(self):
        self.assertEqual([r['url'] for r in self.search(['github.com/python/cpython'])], [
            'https://github.com/python/cpython', 'https://github.com/python/cpython/issues/1'])
        self.assertEqual(len(self.search(['python.org', 'github.com/python/cpython'])), 4)
        self.assertEqual(self.search(['example.com']), [])

    def test_multiple_domain_query_uses_or_not_an_impossible_intersection(self):
        requests = []
        def open_request(request, **kwargs):
            requests.append(request.full_url)
            return io.BytesIO(b'{"results": []}')
        searxng_search.search('release', 3, 'http://127.0.0.1:8888',
            include_domains=['python.org', 'github.com'], opener=open_request)
        self.assertEqual(parse_qs(urlsplit(requests[0]).query)['q'],
                         ['release (site:python.org OR site:github.com)'])

    def test_development_search_uses_web_engines_without_changing_scholarly_or_news_routes(self):
        router = web_search_router.WebSearchRouter(exa_api_key=None, tavily_api_key=None,
            searxng_url='http://127.0.0.1:8888', ledger=Mock())
        for category, expected in [('it', 'general'), ('general', 'general'),
                                   ('publication', 'science'), ('science', 'science'), ('news', 'news')]:
            with self.subTest(category=category), patch.object(searxng_search, 'search',
                    return_value={'results': [], 'note': ''}) as search:
                router._search(web_search_router._validate({'query': 'release', 'category': category,
                    'include_domains': ['python.org']}))
                self.assertEqual(search.call_args.kwargs['category'], expected)
                self.assertEqual(search.call_args.kwargs['include_domains'], ['python.org'])
                router.ledger.reserve_searxng.assert_called()

    def test_empty_engine_failure_is_distinct_from_a_valid_empty_result(self):
        failure = [['brave', 'too many requests'], ['duckduckgo', 'CAPTCHA']]
        for payload, expected_error in (
                ({'results': [], 'unresponsive_engines': failure}, True),
                ({'results': [], 'unresponsive_engines': []}, False),
                ({'results': [], 'unresponsive_engines': [[]]}, False),
                ({'results': [{'title': 'outside filter', 'url': 'https://example.com/'}],
                  'unresponsive_engines': failure}, False)):
            with self.subTest(payload=payload):
                def run():
                    return searxng_search.search('public docs', 3, 'http://127.0.0.1:8888',
                        include_domains=['python.org'],
                        opener=lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
                if expected_error:
                    with self.assertRaisesRegex(searxng_search.SearXNGSearchError, '반복 호출하지 마세요') as error:
                        run()
                    self.assertNotIn('public docs', str(error.exception))
                else:
                    self.assertEqual(run()['results'], [])

    def test_engine_failure_stops_changed_queries_before_network_dispatch(self):
        import tempfile
        from pathlib import Path
        from tools.claude_mcp.usage_ledger import UsageLedger
        with tempfile.TemporaryDirectory() as folder:
            ledger = UsageLedger(Path(folder)/'usage.sqlite3')
            router = web_search_router.WebSearchRouter(exa_api_key=None, tavily_api_key=None,
                searxng_url='http://127.0.0.1:8888', ledger=ledger)
            with patch.object(web_search_router.local_docs_index, 'search', return_value=None), \
                    patch.object(web_search_router.local_docs_index, 'cache_generation', return_value='test'), \
                    patch.object(searxng_search, 'search', side_effect=searxng_search.SearXNGSearchError(
                        'engine unavailable', cooldown_seconds=60)) as request:
                with self.assertRaisesRegex(web_search_router.WebSearchError, 'engine unavailable'):
                    router.search({'query': 'first public query'})
                with self.assertRaisesRegex(web_search_router.WebSearchError, '요청을 다시 보내지 않았습니다'):
                    router.search({'query': 'changed public query'})
                request.assert_called_once()

    def test_unfiltered_search_preserves_results(self):
        self.assertEqual(len(self.search([])), 7)


if __name__ == '__main__':
    unittest.main()
