"""local_docs_index fault tolerance; no network, no GPU."""
import http.client
import unittest
from unittest.mock import patch
from urllib.robotparser import RobotFileParser

from tools.claude_mcp import local_docs_index as docs


class _Headers:
    def get_content_charset(self):
        return "utf-8"


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://docs.example.com/manual/a"

    def read(self, limit):
        raise http.client.IncompleteRead(b"x" * 10, 5)

    headers = _Headers()


class _Opener:
    def open(self, request, timeout=None):
        return _Response()


SOURCE = {"id": "example", "name": "Example", "host": "docs.example.com",
          "path_contains": ["/manual/"], "seed_urls": ["https://docs.example.com/manual/index.html"]}


class FetchFaultTolerance(unittest.TestCase):
    def test_incomplete_read_becomes_local_docs_error(self):
        with patch.object(docs, "_opener", lambda source: _Opener()):
            with self.assertRaises(docs.LocalDocsIndexError):
                docs._fetch("https://docs.example.com/manual/a", SOURCE, limit=1024)

    def test_discovery_falls_back_to_seeds_when_sitemaps_fail(self):
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Allow: /"])
        with patch.object(docs, "_fetch", side_effect=docs.LocalDocsIndexError("문서 출처에 연결하지 못했습니다.")):
            urls = docs._discover_urls(SOURCE, robots, [], 5)
        self.assertEqual(urls, ["https://docs.example.com/manual/index.html"])


if __name__ == "__main__":
    unittest.main()
