"""Route one Claude web_search tool across free APIs and local SearXNG."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import exa_search, local_docs_index, searxng_search, tavily_search
from .search_cache import SearchCache, SearchCacheCancelled
from .usage_ledger import UsageLedger, UsageLedgerError

EXA_RESERVATION_CENTS = 2
EXA_MONTHLY_CAP_CENTS = 800  # Keep $2 of the current $10 Starter allowance uncommitted.
TAVILY_MONTHLY_CAP_CREDITS = 900  # Leave 100 credits for external use and billing-cycle differences.


class WebSearchError(RuntimeError):
    """Safe user-facing router or provider failure."""


WEB_SEARCH_TOOL_DEF = {
    "name": "web_search",
    "description": (
        "Check a short process-memory cache for identical recent requests, then search indexed official "
        "software/AI/game documentation locally when it clearly matches. Otherwise search the public web through Exa first, "
        "Tavily free/basic as backup, then this PC's local SearXNG when API allowance or provider rate limits are reached. "
        "The local fallback has no hourly or daily request-count quota and spaces SearXNG requests by at least 5 seconds, but upstream engines can still throttle or block it; "
        "no search provider can guarantee unlimited use or zero IP blocks. Queries are sent to the selected provider. "
        "Search cache entries are kept in process memory only; recent/news queries have a shorter lifetime. "
        "Never include private code, logs, repository names, credentials, or personal data. "
        "For software, AI, games, papers, GitHub, or Hugging Face, narrow the category or domains and verify claims against primary sources."
    ),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": exa_search.MAX_QUERY_CHARS},
            "count": {"type": "integer", "minimum": 1, "maximum": exa_search.MAX_RESULTS},
            "mode": {
                "type": "string", "enum": list(exa_search.ALLOWED_SEARCH_TYPES),
                "description": "auto is the balanced default; lite trades some search depth for lower cost and latency",
            },
            "category": {
                "type": "string", "enum": ["general", "it", "science", "news", "publication"],
                "description": "General web, software/AI, papers, news, or scholarly publications",
            },
            "include_domains": {
                "type": "array", "maxItems": exa_search.MAX_DOMAINS,
                "items": {"type": "string", "maxLength": 255,
                          "pattern": r"^(\*\.)?[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]+)?$"},
                "description": "Optional domain or host/path filter, such as docs.unity3d.com, dev.epicgames.com, github.com, or huggingface.co",
            },
            "time_range": {
                "type": "string", "enum": ["day", "week", "month", "year"],
                "description": "Optional freshness window; upstream support varies",
            },
            "language": {
                "type": "string", "enum": list(searxng_search.ALLOWED_LANGUAGES),
                "description": "Search language; defaults to auto",
            },
            "published_after": {
                "type": "string", "format": "date",
                "description": "Optional inclusive publication start date in YYYY-MM-DD form",
            },
        },
        "required": ["query"],
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
}


def _validate(args: object) -> dict:
    if not isinstance(args, dict):
        raise WebSearchError("web_search arguments must be an object")
    if set(args) - {"query", "count", "mode", "category", "include_domains", "time_range", "language", "published_after"}:
        raise WebSearchError("web_search received unsupported arguments")
    query = args.get("query")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= exa_search.MAX_QUERY_CHARS:
        raise WebSearchError(f"query must contain 2 to {exa_search.MAX_QUERY_CHARS} characters")
    query = query.strip()
    if "\n" in query or "\r" in query or any(pattern.search(query) for pattern in exa_search.SENSITIVE_PATTERNS):
        raise WebSearchError("검색어에 비공개 코드, 로그 또는 자격 증명이 포함된 것 같아 요청을 보내지 않았습니다.")
    count = args.get("count", exa_search.DEFAULT_RESULTS)
    if type(count) is not int or not 1 <= count <= exa_search.MAX_RESULTS:
        raise WebSearchError(f"count must be an integer between 1 and {exa_search.MAX_RESULTS}")
    mode = args.get("mode", "auto")
    if mode not in exa_search.ALLOWED_SEARCH_TYPES:
        raise WebSearchError("mode must be lite or auto")
    category = args.get("category", "general")
    if category not in ("general", "it", "science", "news", "publication"):
        raise WebSearchError("category must be general, it, science, news, or publication")
    try:
        domains = exa_search._domain_filters(args.get("include_domains"))
    except exa_search.ExaSearchError as exc:
        raise WebSearchError(str(exc)) from None
    time_range = args.get("time_range")
    if time_range is not None and time_range not in ("day", "week", "month", "year"):
        raise WebSearchError("time_range must be day, week, month, or year")
    language = args.get("language", "auto")
    if language not in searxng_search.ALLOWED_LANGUAGES:
        raise WebSearchError("language must be auto, en, en-US, ko, or ko-KR")
    published_after = args.get("published_after")
    if published_after is not None:
        if not isinstance(published_after, str):
            raise WebSearchError("published_after must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(published_after)
        except ValueError:
            raise WebSearchError("published_after must use YYYY-MM-DD") from None
        if parsed.isoformat() != published_after:
            raise WebSearchError("published_after must use YYYY-MM-DD")
    return {"query": query, "count": count, "mode": mode, "category": category,
            "domains": domains, "time_range": time_range, "language": language,
            "published_after": published_after}


class WebSearchRouter:
    """Use Exa, then Tavily, then rate-limited local SearXNG."""

    def __init__(self, *, exa_api_key: str | None, tavily_api_key: str | None,
                 searxng_url: str | None, ledger: UsageLedger | None = None):
        self.exa_api_key = exa_api_key.strip() if isinstance(exa_api_key, str) and exa_api_key.strip() else None
        self.tavily_api_key = tavily_api_key.strip() if isinstance(tavily_api_key, str) and tavily_api_key.strip() else None
        self.searxng_url = (searxng_search.normalize_base_url(searxng_url)
                            if isinstance(searxng_url, str) and searxng_url.strip() else None)
        self.ledger = ledger
        self.cache = SearchCache()

    @property
    def available(self) -> bool:
        return bool(self.exa_api_key or self.tavily_api_key or self.searxng_url)

    def _usage(self) -> UsageLedger:
        if self.ledger is None:
            self.ledger = UsageLedger()
        return self.ledger

    @staticmethod
    def _explain(reason: str | None, provider: str) -> str:
        if reason == "local_monthly_cap":
            return f"{provider} 로컬 안전 한도"
        if reason == "provider_monthly_exhausted":
            return f"{provider} 월간 한도 응답"
        if reason == "provider_cooldown":
            return f"{provider} 일시 제한 대기"
        return f"{provider} 사용 불가"

    @staticmethod
    def _exa_start_date(time_range: str | None) -> str | None:
        days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(time_range)
        if days is None:
            return None
        return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    def search(self, raw_args: object, cancel_event=None) -> dict:
        try:
            args = _validate(raw_args)
            if cancel_event is not None and cancel_event.is_set():
                raise WebSearchError("search cancelled before dispatch")

            def produce():
                try:
                    local_result = local_docs_index.search(args)
                except local_docs_index.LocalDocsIndexError:
                    local_result = None
                if local_result is not None:
                    return local_result
                return self._search(args, cancel_event)

            return self.cache.get_or_compute(
                args, produce, cancel_event, namespace=local_docs_index.cache_generation(),
            )
        except UsageLedgerError as exc:
            raise WebSearchError(str(exc)) from None
        except SearchCacheCancelled:
            raise WebSearchError("웹 검색 요청이 취소되었습니다.") from None

    def _search(self, args: dict, cancel_event=None) -> dict:
        if cancel_event is not None and cancel_event.is_set():
            raise WebSearchError("search cancelled before dispatch")
        ledger = self._usage()
        fallbacks: list[str] = []

        if self.exa_api_key:
            remaining, _reason = ledger.cooldown("exa")
            if remaining:
                fallbacks.append(self._explain("provider_cooldown", "Exa"))
            else:
                admitted, _used, reason = ledger.reserve_monthly("exa", EXA_RESERVATION_CENTS,
                                                                  EXA_MONTHLY_CAP_CENTS)
                if admitted:
                    try:
                        result = exa_search.search(
                            args["query"], args["count"], self.exa_api_key,
                            mode=args["mode"],
                            category=("publication" if args["category"] in ("science", "publication")
                                      else "news" if args["category"] == "news" else None),
                            include_domains=args["domains"],
                            published_after=(args["published_after"] or self._exa_start_date(args["time_range"])),
                            cancel_event=cancel_event,
                        )
                        actual_cost = result.get("costDollars")
                        if (isinstance(actual_cost, (int, float)) and not isinstance(actual_cost, bool)
                                and actual_cost > EXA_RESERVATION_CENTS / 100):
                            ledger.mark_month_exhausted("exa", "cost_above_local_reservation")
                        result["route"] = ["Exa"]
                        return result
                    except exa_search.ExaSearchError as exc:
                        if not exc.fallback_allowed:
                            raise WebSearchError(str(exc)) from None
                        if exc.status_code == 402:
                            ledger.mark_month_exhausted("exa", "provider_monthly_exhausted")
                            fallbacks.append(self._explain("provider_monthly_exhausted", "Exa"))
                        else:
                            seconds = 3600 if exc.status_code in (401, 403) else 60
                            ledger.set_cooldown("exa", seconds, f"http_{exc.status_code}")
                            fallbacks.append(f"Exa HTTP {exc.status_code}")
                else:
                    fallbacks.append(self._explain(reason, "Exa"))

        if self.tavily_api_key:
            remaining, _reason = ledger.cooldown("tavily")
            if remaining:
                fallbacks.append(self._explain("provider_cooldown", "Tavily"))
            else:
                admitted, _used, reason = ledger.reserve_monthly("tavily", 1, TAVILY_MONTHLY_CAP_CREDITS)
                if admitted:
                    topic = "news" if args["category"] == "news" else "general"
                    try:
                        result = tavily_search.search(
                            args["query"], args["count"], self.tavily_api_key,
                            topic=topic,
                            include_domains=[domain.split("/", 1)[0] for domain in args["domains"]],
                            time_range=args["time_range"], published_after=args["published_after"],
                            cancel_event=cancel_event,
                        )
                        usage = result.get("usage", {})
                        credits = usage.get("credits", 1) if isinstance(usage, dict) else 1
                        if credits > 1:
                            ledger.mark_month_exhausted("tavily", "unexpected_credit_cost")
                        result["route"] = (["Tavily"] if not fallbacks else [*fallbacks, "Tavily"])
                        return result
                    except tavily_search.TavilySearchError as exc:
                        if not exc.fallback_allowed:
                            raise WebSearchError(str(exc)) from None
                        if exc.status_code in (432, 433):
                            ledger.mark_month_exhausted("tavily", "provider_monthly_exhausted")
                            fallbacks.append(self._explain("provider_monthly_exhausted", "Tavily"))
                        else:
                            seconds = 3600 if exc.status_code in (401, 403) else 60
                            ledger.set_cooldown("tavily", seconds, f"http_{exc.status_code}")
                            fallbacks.append(f"Tavily HTTP {exc.status_code}")
                else:
                    fallbacks.append(self._explain(reason, "Tavily"))

        if self.searxng_url:
            try:
                ledger.reserve_searxng(cancel_event=cancel_event)
                category = args["category"]
                local_category = ("science" if category in ("science", "publication") else
                                  "news" if category == "news" else "it" if category == "it" else "general")
                result = searxng_search.search(
                    args["query"], args["count"], self.searxng_url,
                    category=local_category, include_domains=args["domains"],
                    time_range=None if args["time_range"] == "week" else args["time_range"],
                    language=args["language"],
                    cancel_event=cancel_event,
                )
                result["route"] = (["Local SearXNG"] if not fallbacks else [*fallbacks, "Local SearXNG"])
                if args["published_after"]:
                    result["note"] += " Exact published_after filtering is not supported by the local fallback."
                if args["time_range"] == "week":
                    result["note"] += " The weekly time window is not applied by the local fallback."
                return result
            except (searxng_search.SearXNGSearchError, UsageLedgerError) as exc:
                raise WebSearchError(str(exc)) from None

        if not fallbacks:
            raise WebSearchError(
                "웹 검색 제공자가 설정되지 않았습니다. EXA_API_KEY/TAVILY_API_KEY를 등록하거나 로컬 SearXNG를 설치하세요."
            )
        raise WebSearchError(
            "사용 가능한 검색 제공자가 없습니다: " + ", ".join(fallbacks) +
            ". API 시간 초과나 서버 오류는 중복 과금을 막기 위해 자동으로 재시도하지 않습니다."
        )
