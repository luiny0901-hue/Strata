"""Short-lived, process-local cache for identical public web searches."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, TimeoutError
from copy import deepcopy
import hashlib
import json
import threading
import time


class SearchCacheCancelled(RuntimeError):
    """A duplicate search waiter was cancelled before the original completed."""


class SearchCache:
    """Reuse recent results without persisting search terms or provider responses."""

    DEFAULT_TTL_SECONDS = 600
    FRESH_TTL_SECONDS = 120
    MAX_ENTRIES = 128
    WAIT_POLL_SECONDS = 0.2

    def __init__(self):
        self._entries: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._inflight: dict[str, Future] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(args: dict, namespace: str = "") -> str:
        canonical = {
            "query": " ".join(args["query"].split()).casefold(),
            "count": args["count"],
            "mode": args["mode"],
            "category": args["category"],
            "domains": sorted(domain.casefold() for domain in args["domains"]),
            "time_range": args["time_range"],
            "language": args["language"].casefold(),
            "published_after": args["published_after"],
            "namespace": namespace,
        }
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _ttl(args: dict) -> int:
        if args["category"] == "news" or args["time_range"] or args["published_after"]:
            return SearchCache.FRESH_TTL_SECONDS
        return SearchCache.DEFAULT_TTL_SECONDS

    def get_or_compute(self, args: dict, producer, cancel_event=None, *, namespace: str = "") -> dict:
        """Return a fresh cache entry or compute once for concurrent identical requests."""
        if cancel_event is not None and cancel_event.is_set():
            raise SearchCacheCancelled("search was cancelled before cache lookup")
        key = self._key(args, namespace)
        query = args["query"]
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise SearchCacheCancelled("search was cancelled before dispatch")
            now = time.monotonic()
            with self._lock:
                cached = self._cached(key, query, now)
                if cached is not None:
                    return cached[0]
                future = self._inflight.get(key)
                owner = future is None
                if owner:
                    future = Future()
                    self._inflight[key] = future

            if not owner:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise SearchCacheCancelled("duplicate search wait was cancelled")
                    try:
                        result = future.result(timeout=self.WAIT_POLL_SECONDS)
                        value = deepcopy(result)
                        value["query"] = query
                        value["cache"] = {"status": "deduplicated", "ageSeconds": 0}
                        return value
                    except TimeoutError:
                        continue

            try:
                result = producer()
            except BaseException as exc:
                with self._lock:
                    self._inflight.pop(key, None)
                    future.set_exception(exc)
                raise
            else:
                stored = deepcopy(result)
                stored.pop("cache", None)
                created_at = time.monotonic()
                stored["_cache_created_at"] = created_at
                with self._lock:
                    self._entries[key] = (created_at + self._ttl(args), stored)
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.MAX_ENTRIES:
                        self._entries.popitem(last=False)
                    self._inflight.pop(key, None)
                    future.set_result(deepcopy(result))
                output = deepcopy(result)
                output["cache"] = {"status": "miss", "ageSeconds": 0}
                return output

    def _cached(self, key: str, query: str, now: float) -> tuple[dict, int] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, stored = entry
        if expires_at <= now:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        value = deepcopy(stored)
        created_at = value.pop("_cache_created_at", now)
        value["query"] = query
        age = max(0, int(now - created_at))
        value["cache"] = {"status": "hit", "ageSeconds": age}
        return value, age
