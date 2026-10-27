"""Small, opt-in Exa Search API adapter for Claude's lazy agent-tools MCP."""
from __future__ import annotations

import json
import math
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = "https://api.exa.ai/search"
MAX_QUERY_CHARS = 400
MAX_RESULTS = 10
DEFAULT_RESULTS = 5
DEFAULT_SEARCH_TYPE = "auto"
ALLOWED_SEARCH_TYPES = ("auto", "lite")
ALLOWED_CATEGORIES = ("publication", "news")
MAX_DOMAINS = 8
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 12
MAX_TITLE_CHARS = 240
MAX_HIGHLIGHT_CHARS = 600
SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[A-Za-z0-9_./+-]{16,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
)


class ExaSearchError(RuntimeError):
    """A safe, user-facing search error that never includes credentials."""

    def __init__(self, message: str, *, status_code: int | None = None, fallback_allowed: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.fallback_allowed = fallback_allowed


class _NoRedirectHandler(HTTPRedirectHandler):
    """Keep the API key confined to the documented API origin."""

    def redirect_request(self, _request, _fp, _code, _message, _headers, _new_url):
        return None


_HTTP_OPENER = build_opener(_NoRedirectHandler)


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
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
        raise ExaSearchError(f"include_domains must be a list of at most {MAX_DOMAINS} domains")
    valid_domain = re.compile(r"^(?:\*\.)?[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~/-]+)?$")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not valid_domain.fullmatch(item.strip()):
            raise ExaSearchError("include_domains must contain hostnames or host/path filters without a URL scheme")
        domain = item.strip().lower()
        if domain not in cleaned:
            cleaned.append(domain)
    return cleaned


def _published_after(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExaSearchError("published_after must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ExaSearchError("published_after must use YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise ExaSearchError("published_after must use YYYY-MM-DD")
    return parsed.isoformat() + "T00:00:00.000Z"


def search(
    query: object,
    count: object,
    api_key: object,
    *,
    mode: object = DEFAULT_SEARCH_TYPE,
    category: object = None,
    include_domains: object = None,
    published_after: object = None,
    opener=None,
    cancel_event=None,
) -> dict:
    """Search Exa once and return compact sources with optional scope filters.

    There are deliberately no retries: repeated attempts can consume API credits.
    The caller owns API-key storage and supplies it only at runtime.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise ExaSearchError("Exa Search is not configured; set EXA_API_KEY and restart Claude Desktop.")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= MAX_QUERY_CHARS:
        raise ExaSearchError(f"query must contain 2 to {MAX_QUERY_CHARS} characters")
    query = query.strip()
    if "\n" in query or "\r" in query:
        raise ExaSearchError("query must be one line; do not send source code, logs, secrets, or private data")
    if any(pattern.search(query) for pattern in SENSITIVE_PATTERNS):
        raise ExaSearchError("query looks like it contains a credential; search was not sent")
    if type(count) is not int or not 1 <= count <= MAX_RESULTS:
        raise ExaSearchError(f"count must be an integer between 1 and {MAX_RESULTS}")
    if mode not in ALLOWED_SEARCH_TYPES:
        raise ExaSearchError("mode must be auto or lite")
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise ExaSearchError("category must be publication when specified")
    domains = _domain_filters(include_domains)
    published_date = _published_after(published_after)
    if cancel_event is not None and cancel_event.is_set():
        raise ExaSearchError("search cancelled before dispatch")

    request_body = {
        "query": query,
        "type": mode,
        "numResults": count,
        "moderation": True,
        "contents": {"highlights": True},
    }
    if domains:
        request_body["includeDomains"] = domains
    if published_date:
        request_body["startPublishedDate"] = published_date
    if category:
        request_body["category"] = category
    payload = json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key.strip(),
        },
        method="POST",
    )
    open_request = opener or _HTTP_OPENER.open
    try:
        with open_request(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403):
            raise ExaSearchError("Exa Search rejected the API key or account access is not active.",
                                 status_code=status, fallback_allowed=True) from None
        if status in (402, 429):
            raise ExaSearchError("Exa Search credits or rate limit are exhausted; no automatic retry was made.",
                                 status_code=status, fallback_allowed=True) from None
        if status >= 500:
            raise ExaSearchError("Exa Search is temporarily unavailable; no automatic retry was made.",
                                 status_code=status) from None
        raise ExaSearchError(f"Exa Search request was rejected (HTTP {status}).", status_code=status) from None
    except (URLError, TimeoutError, OSError):
        raise ExaSearchError("Exa Search connection failed or timed out; no automatic retry was made.") from None

    if len(body) > MAX_RESPONSE_BYTES:
        raise ExaSearchError("Exa Search response exceeded the 1 MiB size limit.")
    try:
        result_payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ExaSearchError("Exa Search returned an invalid response.") from None

    rows = result_payload.get("results") if isinstance(result_payload, dict) else None
    if not isinstance(rows, list):
        raise ExaSearchError("Exa Search response did not contain results.")

    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean_text(row.get("title"), MAX_TITLE_CHARS)
        url = _safe_url(row.get("url"))
        if not title or not url:
            continue
        highlights = row.get("highlights")
        snippets = [_clean_text(item, MAX_HIGHLIGHT_CHARS) for item in highlights[:2]] if isinstance(highlights, list) else []
        snippets = [item for item in snippets if item]
        item = {"title": title, "url": url}
        if snippets:
            item["highlights"] = snippets
        published = _clean_text(row.get("publishedDate"), 40)
        if published:
            item["publishedDate"] = published
        results.append(item)
        if len(results) >= count:
            break

    output = {"provider": "Exa Search", "query": query, "mode": mode, "results": results}
    if category:
        output["category"] = category
    cost = result_payload.get("costDollars") if isinstance(result_payload, dict) else None
    total = cost.get("total") if isinstance(cost, dict) else None
    if isinstance(total, (int, float)) and not isinstance(total, bool) and math.isfinite(total) and 0 <= total <= 1000:
        output["costDollars"] = round(float(total), 8)
    if cancel_event is not None and cancel_event.is_set():
        raise ExaSearchError("search was cancelled after dispatch; verify credit usage before retrying")
    return output
