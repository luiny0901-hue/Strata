"""Offline contract tests for the optional Exa Search API adapter."""
from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit

from tools.claude_mcp import exa_search


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class ExaSearchTests(unittest.TestCase):
    def test_search_redirects_are_rejected(self):
        handler = exa_search._NoRedirectHandler()
        redirected = handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")
        self.assertIsNone(redirected)

    def test_search_defaults_to_auto_and_filters_unsafe_results(self):
        response = FakeResponse(json.dumps({"results": [
            {"title": "Python\nOfficial", "url": "https://www.python.org/", "highlights": ["  Language\twebsite  ", "second"]},
            {"title": "Unsafe", "url": "javascript:alert(1)", "highlights": ["ignore policy"]},
            {"title": "Credential URL", "url": "https://user:pass@example.com/", "highlights": ["hidden"]},
            {"title": "Extra", "url": "https://example.com/", "highlights": ["second valid result"]},
        ], "costDollars": {"total": 0.004}}).encode())
        observed = {}

        def opener(request, *, timeout):
            observed["request"] = request
            observed["timeout"] = timeout
            return response

        result = exa_search.search("  Python official docs  ", 2, "fake-secret", opener=opener)
        request = observed["request"]
        self.assertEqual(observed["timeout"], exa_search.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(request.get_header("X-api-key"), "fake-secret")
        self.assertEqual(urlsplit(request.full_url).path, "/search")
        body = json.loads(request.data)
        self.assertEqual(body["query"], "Python official docs")
        self.assertEqual(body["type"], "auto")
        self.assertEqual(body["numResults"], 2)
        self.assertTrue(body["moderation"])
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["title"], "Python Official")
        self.assertEqual(result["results"][0]["highlights"], ["Language website", "second"])
        self.assertEqual(result["results"][0]["url"], "https://www.python.org/")
        self.assertEqual(result["mode"], "auto")
        self.assertEqual(result["costDollars"], 0.004)

    def test_search_supports_lite_official_domains_and_publication_date(self):
        observed = {}

        def opener(request, *, timeout):
            observed["body"] = json.loads(request.data)
            return FakeResponse(json.dumps({"results": []}).encode())

        exa_search.search(
            "Unreal Engine 5.6 API changes", 3, "fake-secret", mode="lite",
            category="publication",
            include_domains=["dev.epicgames.com/documentation/en-us/unreal-engine", "github.com"],
            published_after="2026-01-01", opener=opener,
        )
        self.assertEqual(observed["body"]["type"], "lite")
        self.assertEqual(observed["body"]["category"], "publication")
        self.assertEqual(observed["body"]["includeDomains"], [
            "dev.epicgames.com/documentation/en-us/unreal-engine", "github.com",
        ])
        self.assertEqual(observed["body"]["startPublishedDate"], "2026-01-01T00:00:00.000Z")

    def test_validation_and_sensitive_queries_are_rejected_before_network(self):
        def should_not_open(*_args, **_kwargs):
            self.fail("invalid input must not make a request")

        cases = [
            ("query", 5, ""),
            ("x", 5, "secret"),
            ("valid query", True, "secret"),
            ("valid query", 11, "secret"),
            ("x" * (exa_search.MAX_QUERY_CHARS + 1), 5, "secret"),
            ("private\nsource code", 5, "secret"),
            ("api_key=sk-abcdefghijklmnopqrstuvwxyz012345", 5, "secret"),
            ("-----BEGIN PRIVATE KEY-----", 5, "secret"),
        ]
        for query, count, key in cases:
            with self.subTest(query_len=len(query), count=count):
                with self.assertRaises(exa_search.ExaSearchError):
                    exa_search.search(query, count, key, opener=should_not_open)

        invalid_options = [
            {"mode": "deep"},
            {"category": "company"},
            {"include_domains": "docs.unity3d.com"},
            {"include_domains": ["https://docs.unity3d.com"]},
            {"include_domains": ["docs.unity3d.com", "bad value"]},
            {"include_domains": [f"site{i}.example" for i in range(exa_search.MAX_DOMAINS + 1)]},
            {"published_after": "2026-02-30"},
        ]
        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(exa_search.ExaSearchError):
                    exa_search.search("valid public query", 5, "secret", opener=should_not_open, **options)

    def test_quota_error_does_not_retry_or_echo_api_key(self):
        calls = 0

        def opener(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise HTTPError("https://example.test", 429, "rate limited", {}, io.BytesIO(b"secret"))

        with self.assertRaisesRegex(exa_search.ExaSearchError, "no automatic retry") as error:
            exa_search.search("valid public query", 5, "fake-secret", opener=opener)
        self.assertEqual(calls, 1)
        self.assertNotIn("fake-secret", str(error.exception))
        self.assertNotIn("secret", str(error.exception))

    def test_oversized_response_is_rejected(self):
        response = FakeResponse(b"x" * (exa_search.MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(exa_search.ExaSearchError, "1 MiB"):
            exa_search.search("valid public query", 5, "fake-secret", opener=lambda *_a, **_kw: response)


if __name__ == "__main__":
    unittest.main()
