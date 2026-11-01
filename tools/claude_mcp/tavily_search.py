"""Bounded adapter for Tavily's free/basic Search API."""
from __future__ import annotations

import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .exa_search import SENSITIVE_PATTERNS, _clean_text, _domain_filters, _safe_url

ENDPOINT = "https://api.tavily.com/search"
MAX_QUERY_CHARS = 400
MAX_RESULTS = 10
DEFAULT_RESULTS = 5
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 15
ALLOWED_TIME_RANGES = ("day", "week", "month", "year")


class TavilySearchError(RuntimeError):
    """Safe user-facing error with explicit status-based fallback eligibility."""

    def __init__(self, message: str, *, status_code: int | None = None, fallback_allowed: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.fallback_allowed = fallback_allowed


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, _request, _fp, _code, _message, _new_url):
        return None


_HTTP_OPENER = build_opener(_NoRedirectHandler)


def _start_date(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TavilySearchError("published_after must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise TavilySearchError("published_after must use YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise TavilySearchError("published_after must use YYYY-MM-DD")
    return parsed.isoformat()


def search(
    query: object,
    count: object,
    api_key: object,
    *,
    topic: object = "general",
    include_domains: object = None,
    time_range: object = None,
    published_after: object = None,
    opener=None,
    cancel_event=None,
) -> dict:
    """Perform one basic search (1 API credit) without retries or page extraction."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise TavilySearchError("Tavily Search is not configured; set its key with the local search-key setup command.")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= MAX_QUERY_CHARS:
        raise TavilySearchError(f"query must contain 2 to {MAX_QUERY_CHARS} characters")
    query = query.strip()
    if "\n" in query or "\r" in query:
        raise TavilySearchError("query must be one line; do not send source code, logs, secrets, or private data")
    if any(pattern.search(query) for pattern in SENSITIVE_PATTERNS):
        raise TavilySearchError("query looks like it contains a credential; search was not sent")
    if type(count) is not int or not 1 <= count <= MAX_RESULTS:
        raise TavilySearchError(f"count must be an integer between 1 and {MAX_RESULTS}")
    if topic not in ("general", "news", "finance"):
        raise TavilySearchError("topic must be general, news, or finance")
    if time_range is not None and time_range not in ALLOWED_TIME_RANGES:
        raise TavilySearchError("time_range must be day, week, month, or year")
    domains = _domain_filters(include_domains)
    since = _start_date(published_after)
    if cancel_event is not None and cancel_event.is_set():
        raise TavilySearchError("search cancelled before dispatch")

    body = {
        "query": query,
        "search_depth": "basic",
        "max_results": count,
        "topic": topic,
        "include_domains": domains,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_usage": True,
        "safe_search": True,
    }
    if time_range:
        body["time_range"] = time_range
    if since:
        body["start_date"] = since
        body["filter_by_published_date"] = True
    request = Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key.strip(),
        },
        method="POST",
    )
    try:
        with (opener or _HTTP_OPENER.open)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403):
            raise TavilySearchError("Tavily rejected the API key or account access is not active.",
                                    status_code=status, fallback_allowed=True) from None
        if status in (432, 433):
            raise TavilySearchError("Tavily free-plan credits or monthly plan limit are exhausted; no retry was made.",
                                    status_code=status, fallback_allowed=True) from None
        if status == 429:
            raise TavilySearchError("Tavily credits or request rate are exhausted; no retry was made.",
                                    status_code=status, fallback_allowed=True) from None
        if status >= 500:
            raise TavilySearchError("Tavily is temporarily unavailable; no retry was made.",
                                    status_code=status) from None
        raise TavilySearchError(f"Tavily rejected the request (HTTP {status}).", status_code=status) from None
    except (URLError, TimeoutError, OSError):
        raise TavilySearchError("Tavily connection failed or timed out; no retry was made.") from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise TavilySearchError("Tavily response exceeded the 1 MiB size limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise TavilySearchError("Tavily returned an invalid response.") from None
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise TavilySearchError("Tavily response did not contain results.")

    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean_text(row.get("title"), 240)
        url = _safe_url(row.get("url"))
        if not title or not url:
            continue
        item = {"title": title, "url": url}
        snippet = _clean_text(row.get("content"), 700)
        if snippet:
            item["snippet"] = snippet
        published = _clean_text(row.get("published_date"), 40)
        if published:
            item["publishedDate"] = published
        results.append(item)
        if len(results) >= count:
            break

    output = {"provider": "Tavily", "query": query, "topic": topic, "results": results}
    usage = payload.get("usage") if isinstance(payload, dict) else None
    credits = usage.get("credits") if isinstance(usage, dict) else None
    if type(credits) is int and 0 <= credits <= 1000:
        output["usage"] = {"credits": credits}
    if cancel_event is not None and cancel_event.is_set():
        raise TavilySearchError("search was cancelled after dispatch; verify credit usage before retrying")
    return output
