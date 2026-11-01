"""Bounded adapter for a loopback SearXNG instance."""
from __future__ import annotations

import html
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .exa_search import SENSITIVE_PATTERNS

MAX_QUERY_CHARS = 400
MAX_RESULTS = 10
DEFAULT_RESULTS = 5
MAX_DOMAINS = 8
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 15
MAX_TITLE_CHARS = 240
MAX_CONTENT_CHARS = 700
ALLOWED_CATEGORIES = ("general", "it", "science", "news")
ALLOWED_TIME_RANGES = ("day", "month", "year")
ALLOWED_LANGUAGES = ("auto", "en", "en-US", "ko", "ko-KR")


class SearXNGSearchError(RuntimeError):
    """Safe user-facing local search errors."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, _request, _fp, _code, _message, _headers, _new_url):
        return None


_HTTP_OPENER = build_opener(_NoRedirectHandler)


def normalize_base_url(value: object) -> str:
    """Accept only a plain HTTP loopback origin; search queries stay on this PC."""
    if not isinstance(value, str) or len(value) > 255:
        raise SearXNGSearchError("SEARXNG_URL must point to a local HTTP SearXNG service")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port or 80
    except ValueError:
        raise SearXNGSearchError("SEARXNG_URL is invalid") from None
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or not 1 <= port <= 65535):
        raise SearXNGSearchError("SEARXNG_URL must be a plain HTTP loopback origin such as http://127.0.0.1:8888")
    return f"http://{parsed.hostname}:{port}"


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<[^>]{0,500}>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _safe_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return ""
        return value
    except ValueError:
        return ""


def _domain_filters(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_DOMAINS:
        raise SearXNGSearchError(f"include_domains must be a list of at most {MAX_DOMAINS} domains")
    valid_domain = re.compile(r"^(?:\*\.)?[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~/-]+)?$")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not valid_domain.fullmatch(item.strip()):
            raise SearXNGSearchError("include_domains must contain hostnames or host/path filters without a URL scheme")
        domain = item.strip().lower()
        if domain not in cleaned:
            cleaned.append(domain)
    return cleaned


def search(
    query: object,
    count: object,
    base_url: object,
    *,
    category: object = None,
    include_domains: object = None,
    time_range: object = None,
    language: object = "auto",
    opener=None,
    cancel_event=None,
) -> dict:
    """Issue one bounded request to local SearXNG; never retries blocked engines."""
    base_url = normalize_base_url(base_url)
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= MAX_QUERY_CHARS:
        raise SearXNGSearchError(f"query must contain 2 to {MAX_QUERY_CHARS} characters")
    query = query.strip()
    if "\n" in query or "\r" in query:
        raise SearXNGSearchError("query must be one line; do not send source code, logs, secrets, or private data")
    if any(pattern.search(query) for pattern in SENSITIVE_PATTERNS):
        raise SearXNGSearchError("query looks like it contains a credential; search was not sent")
    if type(count) is not int or not 1 <= count <= MAX_RESULTS:
        raise SearXNGSearchError(f"count must be an integer between 1 and {MAX_RESULTS}")
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise SearXNGSearchError("category must be general, it, science, or news")
    if time_range is not None and time_range not in ALLOWED_TIME_RANGES:
        raise SearXNGSearchError("time_range must be day, month, or year")
    if language not in ALLOWED_LANGUAGES:
        raise SearXNGSearchError("language must be auto, en, en-US, ko, or ko-KR")
    domains = _domain_filters(include_domains)
    if cancel_event is not None and cancel_event.is_set():
        raise SearXNGSearchError("search cancelled before dispatch")

    scoped_query = query
    if domains:
        scoped_query += " " + " ".join(f"site:{domain}" for domain in domains)
    params = {"q": scoped_query, "format": "json", "language": language, "safesearch": "1"}
    if category:
        params["categories"] = category
    if time_range:
        params["time_range"] = time_range
    request = Request(
        base_url + "/search?" + urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "StrataAgentTools/1.0"},
        method="GET",
    )
    try:
        with (opener or _HTTP_OPENER.open)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status == 403:
            raise SearXNGSearchError("Local SearXNG refused JSON; enable json under search.formats and restart it.") from None
        if status == 429:
            raise SearXNGSearchError("SearXNG rate-limited this request; no retry was made.") from None
        if status >= 500:
            raise SearXNGSearchError("SearXNG or its upstream engines are temporarily unavailable; no retry was made.") from None
        raise SearXNGSearchError(f"Local SearXNG rejected the request (HTTP {status}).") from None
    except (URLError, TimeoutError, OSError):
        raise SearXNGSearchError(
            "Local SearXNG is unavailable or timed out; start the Strata free web-search service. No retry was made."
        ) from None

    if len(body) > MAX_RESPONSE_BYTES:
        raise SearXNGSearchError("SearXNG response exceeded the 1 MiB size limit.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SearXNGSearchError("SearXNG returned an invalid response.") from None
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise SearXNGSearchError("SearXNG response did not contain results.")

    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean_text(row.get("title"), MAX_TITLE_CHARS)
        url = _safe_url(row.get("url"))
        if not title or not url:
            continue
        item = {"title": title, "url": url}
        content = _clean_text(row.get("content"), MAX_CONTENT_CHARS)
        if content:
            item["snippet"] = content
        engine = _clean_text(row.get("engine"), 80)
        if engine:
            item["engine"] = engine
        published = _clean_text(row.get("publishedDate"), 40)
        if published:
            item["publishedDate"] = published
        results.append(item)
        if len(results) >= count:
            break

    output = {
        "provider": "Local SearXNG",
        "query": query,
        "category": category or "general",
        "results": results,
        "note": "Results come from external search engines; their availability and rate limits vary.",
    }
    failed = payload.get("unresponsive_engines") if isinstance(payload, dict) else None
    if isinstance(failed, list):
        output["unresponsive_engines"] = [
            [_clean_text(part, 80) for part in row[:2] if isinstance(part, (str, int, float))]
            for row in failed[:8] if isinstance(row, list)
        ]
    if cancel_event is not None and cancel_event.is_set():
        raise SearXNGSearchError("search was cancelled after dispatch; verify before retrying")
    return output
