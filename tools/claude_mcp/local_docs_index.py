"""Refresh and search a small, robots-aware index of selected official documentation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import gzip
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_SITEMAP_BYTES = 4 * 1024 * 1024
MAX_SITEMAPS_PER_SOURCE = 12
MAX_PAGES_PER_SOURCE = 100
MAX_INDEXED_PAGES_PER_SOURCE = 300
MAX_BODY_CHARS = 60_000
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "StrataLocalDocsIndexer/1.0 (curated, low-rate documentation index)"
CATALOG_PATH = Path(__file__).with_name("local_docs_sources.json")


class LocalDocsIndexError(RuntimeError):
    """A safe local index or bounded source-refresh failure."""


def _default_path() -> Path:
    override = os.environ.get("STRATA_WEB_SEARCH_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser() / "docs.sqlite3"
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "Strata" / "WebSearch" / "docs.sqlite3"
    return Path.home() / ".local" / "state" / "strata" / "web-search" / "docs.sqlite3"


def _catalog() -> list[dict]:
    try:
        value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LocalDocsIndexError("로컬 문서 출처 목록을 읽지 못했습니다.") from None
    sources = value.get("sources") if isinstance(value, dict) and value.get("version") == 1 else None
    if not isinstance(sources, list):
        raise LocalDocsIndexError("로컬 문서 출처 목록 형식이 올바르지 않습니다.")
    return sources


def _valid_source(source: dict) -> bool:
    if not isinstance(source, dict):
        return False
    source_id, host = source.get("id"), source.get("host")
    paths, seeds = source.get("path_contains"), source.get("seed_urls")
    if (not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", source_id)
            or not isinstance(host, str) or not re.fullmatch(r"[a-z0-9.-]{1,253}", host)
            or not isinstance(paths, list) or not paths or not all(isinstance(x, str) and x.startswith("/") for x in paths)
            or not isinstance(seeds, list) or not all(_same_host(url, host) for url in seeds)):
        return False
    return True


def _same_host(url: object, host: str) -> bool:
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.hostname == host and not parsed.username and not parsed.password
    except ValueError:
        return False


def _in_scope(url: object, source: dict) -> bool:
    if not _same_host(url, source["host"]):
        return False
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        return False
    path = parsed.path.casefold()
    return any(marker.casefold() in path for marker in source["path_contains"])


class _ScopedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if not _same_host(new_url, self.host):
            return None
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _opener(source: dict):
    return build_opener(_ScopedRedirectHandler(source["host"]))


def _fetch(url: str, source: dict, *, limit: int) -> tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}, method="GET")
    try:
        with _opener(source).open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not _same_host(final_url, source["host"]):
                raise LocalDocsIndexError("출처 외부로 이동한 응답은 저장하지 않았습니다.")
            body = response.read(limit + 1)
            if len(body) > limit:
                raise LocalDocsIndexError("문서 응답이 허용 크기를 넘어 저장하지 않았습니다.")
            return body, final_url, response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        status = exc.code
        exc.close()
        raise LocalDocsIndexError(f"문서 출처가 HTTP {status}를 반환했습니다.") from None
    except (URLError, TimeoutError, OSError):
        raise LocalDocsIndexError("문서 출처에 연결하지 못했습니다.") from None


def _robots(source: dict) -> tuple[RobotFileParser, list[str]]:
    robots_url = f"https://{source['host']}/robots.txt"
    parser = RobotFileParser(robots_url)
    try:
        body, _, charset = _fetch(robots_url, source, limit=512 * 1024)
    except LocalDocsIndexError as exc:
        if "HTTP 404" in str(exc):
            parser.parse([])
            return parser, []
        raise
    lines = body.decode(charset, errors="replace").splitlines()
    parser.parse(lines)
    sitemaps = []
    for line in lines:
        key, separator, value = line.partition(":")
        if separator and key.strip().casefold() == "sitemap":
            sitemap = value.strip()
            if _same_host(sitemap, source["host"]):
                sitemaps.append(sitemap)
    return parser, sitemaps[:MAX_SITEMAPS_PER_SOURCE]


def _xml_loc_rows(body: bytes) -> tuple[bool, list[tuple[str, str | None]]]:
    if body.startswith(b"\x1f\x8b"):
        try:
            body = gzip.decompress(body)
        except OSError:
            raise LocalDocsIndexError("사이트맵 압축 형식이 올바르지 않습니다.") from None
        if len(body) > MAX_SITEMAP_BYTES:
            raise LocalDocsIndexError("압축 해제한 사이트맵이 허용 크기를 넘었습니다.")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise LocalDocsIndexError("사이트맵 XML을 읽지 못했습니다.") from None
    is_index = root.tag.rsplit("}", 1)[-1].casefold() == "sitemapindex"
    rows = []
    for item in list(root):
        fields = {child.tag.rsplit("}", 1)[-1].casefold(): (child.text or "").strip() for child in list(item)}
        loc = fields.get("loc")
        if loc:
            rows.append((loc, fields.get("lastmod") or None))
    return is_index, rows


def _discover_urls(source: dict, robots: RobotFileParser, sitemap_urls: list[str], max_pages: int) -> list[str]:
    if not sitemap_urls:
        sitemap_urls = [f"https://{source['host']}/sitemap.xml",
                        f"https://{source['host']}/sitemap_index.xml"]
    pending = list(sitemap_urls[:MAX_SITEMAPS_PER_SOURCE])
    page_rows: list[tuple[str, str | None]] = []
    visited_sitemaps: set[str] = set()
    while pending and len(visited_sitemaps) < MAX_SITEMAPS_PER_SOURCE and len(page_rows) < max_pages * 4:
        sitemap = pending.pop(0)
        if sitemap in visited_sitemaps or not _same_host(sitemap, source["host"]):
            continue
        if not robots.can_fetch(USER_AGENT, sitemap):
            continue
        visited_sitemaps.add(sitemap)
        if len(visited_sitemaps) > 1:
            time.sleep(1)
        try:
            body, _, _ = _fetch(sitemap, source, limit=MAX_SITEMAP_BYTES)
            is_index, rows = _xml_loc_rows(body)
        except LocalDocsIndexError:
            continue
        for url, lastmod in rows:
            if is_index:
                if _same_host(url, source["host"]) and url not in visited_sitemaps:
                    pending.append(url)
            elif _in_scope(url, source) and robots.can_fetch(USER_AGENT, url):
                page_rows.append((url, lastmod))
                if len(page_rows) >= max_pages * 4:
                    break
    seeds = [(url, None) for url in source["seed_urls"] if _in_scope(url, source) and robots.can_fetch(USER_AGENT, url)]
    seen = set()
    candidates = []
    for row in [*seeds, *page_rows]:
        if row[0] not in seen:
            seen.add(row[0])
            candidates.append(row)
    if any(lastmod for _, lastmod in candidates):
        candidates.sort(key=lambda row: row[1] or "", reverse=True)
    return [url for url, _ in candidates[:max_pages]]


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.links: list[str] = []
        self._title = False
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag == "a" and len(self.links) < 500:
            href = next((value for key, value in attrs if key.casefold() == "href"), None)
            if isinstance(href, str) and href.strip():
                self.links.append(href.strip())
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._title = True
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.body_parts.append(" ")

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._title = False
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.body_parts.append(" ")

    def handle_data(self, data):
        if self._title:
            self.title_parts.append(data)
        if not self._skip_depth:
            self.body_parts.append(data)

    def result(self) -> tuple[str, str, list[str]]:
        title = re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()[:240]
        body = re.sub(r"\s+", " ", " ".join(self.body_parts)).strip()[:MAX_BODY_CHARS]
        return title, body, self.links


def _extract(body: bytes, charset: str) -> tuple[str, str, list[str]]:
    text = body.decode(charset, errors="replace")
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return parser.result()


def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5("
        "source_id UNINDEXED, source_name UNINDEXED, title, url UNINDEXED, body, indexed_at UNINDEXED, "
        "tokenize='unicode61')"
    )
    return connection


def refresh(source_ids: list[str], *, max_pages: int = 10, delay_seconds: float = 1.0,
            path: Path | None = None) -> dict:
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES_PER_SOURCE:
        raise LocalDocsIndexError(f"max_pages must be between 1 and {MAX_PAGES_PER_SOURCE}")
    if not isinstance(delay_seconds, (int, float)) or not 1 <= delay_seconds <= 30:
        raise LocalDocsIndexError("delay_seconds must be between 1 and 30")
    sources = [item for item in _catalog() if _valid_source(item) and item["id"] in source_ids]
    missing = set(source_ids) - {item["id"] for item in sources}
    if missing:
        raise LocalDocsIndexError("알 수 없는 문서 출처 ID입니다: " + ", ".join(sorted(missing)))
    if not sources:
        raise LocalDocsIndexError("갱신할 문서 출처가 선택되지 않았습니다.")
    index_path = path or _default_path()
    summaries = []
    for source in sources:
        fetched = []
        errors = []
        attempted = 0
        try:
            robots, sitemaps = _robots(source)
            queue = _discover_urls(source, robots, sitemaps, max_pages)
            seen: set[str] = set()
            while queue and attempted < max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                if attempted:
                    time.sleep(delay_seconds)
                attempted += 1
                try:
                    if not robots.can_fetch(USER_AGENT, url):
                        continue
                    body, final_url, charset = _fetch(url, source, limit=MAX_PAGE_BYTES)
                    title, text, links = _extract(body, charset)
                    if title and text:
                        fetched.append((source["id"], source["name"], title, final_url, text))
                    for href in links:
                        candidate = urljoin(final_url, href)
                        parsed = urlsplit(candidate)
                        candidate = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
                        if (_in_scope(candidate, source) and robots.can_fetch(USER_AGENT, candidate)
                                and candidate not in seen and candidate not in queue):
                            queue.append(candidate)
                except LocalDocsIndexError as exc:
                    errors.append(str(exc))
        except LocalDocsIndexError as exc:
            errors.append(str(exc))

        if fetched:
            indexed_at = int(time.time())
            connection = None
            try:
                connection = _connect(index_path)
                with connection:
                    for row in fetched:
                        connection.execute("DELETE FROM documents WHERE source_id=? AND url=?",
                                           (source["id"], row[3]))
                    connection.executemany(
                        "INSERT INTO documents(source_id,source_name,title,url,body,indexed_at) VALUES(?,?,?,?,?,?)",
                        [(*row, indexed_at) for row in fetched],
                    )
                    connection.execute(
                        "DELETE FROM documents WHERE rowid IN ("
                        "SELECT rowid FROM documents WHERE source_id=? "
                        "ORDER BY CAST(indexed_at AS INTEGER) DESC,rowid DESC LIMIT -1 OFFSET ?) ",
                        (source["id"], MAX_INDEXED_PAGES_PER_SOURCE),
                    )
            except sqlite3.Error:
                raise LocalDocsIndexError("로컬 문서 색인을 저장하지 못했습니다.") from None
            finally:
                if connection is not None:
                    connection.close()
        summaries.append({
            "id": source["id"], "name": source["name"], "indexedPages": len(fetched),
            "preservedPreviousIndex": not bool(fetched), "maxStoredPages": MAX_INDEXED_PAGES_PER_SOURCE,
            "warnings": errors[:3],
        })
    return {"database": str(index_path), "sources": summaries}


def status(path: Path | None = None) -> dict:
    index_path = path or _default_path()
    if not index_path.exists():
        return {"database": str(index_path), "indexedPages": 0, "sources": []}
    connection = None
    try:
        connection = sqlite3.connect(index_path, timeout=5)
        rows = connection.execute(
            "SELECT source_id, source_name, COUNT(*), MAX(indexed_at) FROM documents GROUP BY source_id, source_name ORDER BY source_id"
        ).fetchall()
    except sqlite3.Error:
        raise LocalDocsIndexError("로컬 문서 색인 상태를 읽지 못했습니다.") from None
    finally:
        if connection is not None:
            connection.close()
    sources = []
    total = 0
    for source_id, name, count, indexed_at in rows:
        count = int(count)
        total += count
        stamp = datetime.fromtimestamp(int(indexed_at), timezone.utc).isoformat().replace("+00:00", "Z")
        sources.append({"id": source_id, "name": name, "indexedPages": count, "indexedAtUtc": stamp})
    return {"database": str(index_path), "indexedPages": total, "sources": sources}


def cache_generation(path: Path | None = None) -> str:
    """Change the query-cache namespace when the local index or its WAL changes."""
    index_path = path or _default_path()
    parts = []
    for candidate in (index_path, Path(str(index_path) + "-wal")):
        try:
            stat = candidate.stat()
            parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append("missing")
    return "|".join(parts)


def _query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(token for token in re.findall(r"[\w]+", query, flags=re.UNICODE)
                              if len(token) >= 2))[:12]


def _matches_requested_domain(source: dict, domain_filter: str) -> bool:
    host_filter, separator, path_filter = domain_filter.partition("/")
    host_filter = host_filter.removeprefix("*.").casefold()
    source_host = source["host"].casefold()
    if source_host != host_filter:
        return False
    return not separator or any(path_filter.casefold() in marker.casefold() for marker in source["path_contains"])


def _snippet(body: str, terms: list[str], limit: int = 520) -> str:
    folded = body.casefold()
    positions = [folded.find(term.casefold()) for term in terms]
    positions = [position for position in positions if position >= 0]
    start = max(0, min(positions) - limit // 4) if positions else 0
    end = min(len(body), start + limit)
    snippet = body[start:end].strip()
    if start:
        snippet = "…" + snippet
    if end < len(body):
        snippet += "…"
    return snippet


def search(args: dict, *, path: Path | None = None) -> dict | None:
    """Search indexed official docs when query scope/freshness makes local results safe."""
    if args.get("category") == "news" or args.get("time_range") or args.get("published_after"):
        return None
    index_path = path or _default_path()
    if not index_path.is_file():
        return None
    all_sources = [source for source in _catalog() if _valid_source(source)]
    domains = args["domains"]
    if domains:
        selected = [source for source in all_sources
                    if any(_matches_requested_domain(source, domain) for domain in domains)]
        # Do not let an incomplete local index satisfy a mixed or unsupported domain request.
        if not selected or any(not any(_matches_requested_domain(source, domain) for source in selected)
                               for domain in domains):
            return None
        explicit_scope = True
    elif args["category"] == "it":
        selected = all_sources
        explicit_scope = False
    else:
        return None
    terms = _query_terms(args["query"])
    if not terms:
        return None
    match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    placeholders = ",".join("?" for _ in selected)
    connection = None
    try:
        connection = sqlite3.connect(str(index_path), timeout=2)
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            f"SELECT source_id,source_name,title,url,body,indexed_at,bm25(documents) "
            f"FROM documents WHERE documents MATCH ? AND source_id IN ({placeholders}) "
            "ORDER BY bm25(documents), indexed_at DESC LIMIT ?",
            [match, *[source["id"] for source in selected], args["count"]],
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        if connection is not None:
            connection.close()
    if not rows or (not explicit_scope and len(rows) < min(3, args["count"])):
        return None
    results = []
    for _source_id, source_name, title, url, body, indexed_at, _rank in rows:
        stamp = datetime.fromtimestamp(int(indexed_at), timezone.utc).isoformat().replace("+00:00", "Z")
        results.append({
            "title": title, "url": url, "snippet": _snippet(body, terms),
            "source": source_name, "indexedAtUtc": stamp,
        })
    return {
        "provider": "Local curated documentation index",
        "query": args["query"], "results": results, "route": ["Local docs index"],
        "note": "검색 결과는 저장된 공식 문서 스냅샷입니다. 최신성 필터 요청은 외부 검색으로 전달됩니다.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sources", help="list curated documentation sources")
    commands.add_parser("status", help="show the current local index contents")
    refresh_parser = commands.add_parser("refresh", help="update a bounded set of selected official docs")
    group = refresh_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", action="append", help="curated source ID; repeat to select more than one")
    group.add_argument("--all", action="store_true", help="refresh every curated source")
    refresh_parser.add_argument("--max-pages", type=int, default=10,
                                help=f"maximum pages per source (1-{MAX_PAGES_PER_SOURCE}; default 10)")
    refresh_parser.add_argument("--delay-seconds", type=float, default=1.0,
                                help="minimum pause between page downloads (1-30; default 1)")
    args = parser.parse_args(argv)
    try:
        if args.command == "sources":
            result = [{"id": source["id"], "name": source["name"], "host": source["host"]}
                      for source in _catalog() if _valid_source(source)]
        elif args.command == "status":
            result = status()
        else:
            selected = [source["id"] for source in _catalog() if _valid_source(source)] if args.all else args.source
            result = refresh(selected, max_pages=args.max_pages, delay_seconds=args.delay_seconds)
    except (LocalDocsIndexError, OSError, ValueError) as exc:
        parser.exit(2, f"로컬 문서 색인: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
