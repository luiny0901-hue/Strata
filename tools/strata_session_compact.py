#!/usr/bin/env python3
"""Compact oversized Claude Code sessions after the server window shrinks.

When the context switch moves from the 1M launcher back to the 262K launcher,
sessions that grew past the new window keep failing with the server's
"request exceeds the context window" refusal because their own compaction
would also re-read the whole oversized conversation. This tool performs that
compaction externally: it asks the now-running (smaller) server to summarize
each session in window-sized chunks, then appends a compact boundary and a
continuation summary in the same shape the harness writes natively, so the
same session resumes inside the new window. Opt-in; sessions are only touched
when idle and oversized, and a backup copy is written before any append.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SERVER_URL = "http://127.0.0.1:8080"
KEY_FILE = ".config/strata/STRATA_API_KEY"
SESSION_FILE = re.compile(r"^[0-9a-fA-F-]{36}\.jsonl$")
# Kept well below 262,144 so the request itself never needs the old window.
DEFAULT_CHUNK_TOKENS = 150_000
DEFAULT_RESERVE_TOKENS = 49_152
DEFAULT_IDLE_MINUTES = 60
SUMMARY_OUTPUT_TOKENS = 2_048
# Rough character-per-token factor for planning only; exact counts come from
# the server's /v1/messages/count_tokens.
CHARS_PER_TOKEN = 4
COMPACT_TRIGGER = "manual"
SUMMARY_PREFIX = (
    "This session is being continued from a previous conversation that ran "
    "out of context. The summary below covers the earlier portion of the "
    "conversation.\n\n"
)
SUMMARY_SYSTEM = (
    "You compress coding-session transcripts for continuation in a new "
    "context window. Write an English continuation summary with these "
    "sections: Primary Request and Intent; Key Technical Concepts; Files "
    "and Code Sections; Errors and Fixes; Problem Solving; All User Messages; "
    "Pending Tasks; Current Work; Optional Next Step. Preserve exact file "
    "paths, commands, identifiers, and error text. Return only the summary."
)
CHUNK_INSTRUCTION = (
    "Compress the transcript excerpt above together with the carry-over "
    "summary above it (if any) into the same sectioned summary. Keep every "
    "fact that later turns depend on."
)
FINAL_INSTRUCTION = (
    "Compress everything above into the final sectioned continuation summary. "
    "State what the latest turns were doing and what remains pending."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def load_api_key(home: Path) -> str | None:
    path = home / KEY_FILE
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


class StrataClient:
    """Minimal chat/count client for the running Strata server."""

    def __init__(self, server_url: str, api_key: str | None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _request(self, route: str, body: dict | None, timeout: int) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.server_url + route, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def health(self) -> dict:
        return self._request("/health", None, 15)

    def count_tokens(self, model: str, text: str) -> int:
        result = self._request(
            "/v1/messages/count_tokens",
            {"model": model, "messages": [{"role": "user", "content": text}]},
            120,
        )
        return int(result["input_tokens"])

    def summarize(self, model: str, carry_over: str, excerpt: str, instruction: str) -> str:
        parts = []
        if carry_over:
            parts.append("Carry-over summary so far:\n" + carry_over + "\n\n")
        parts.append("Transcript excerpt:\n" + excerpt + "\n\n" + instruction)
        result = self._request(
            "/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": "".join(parts)}],
                "max_tokens": SUMMARY_OUTPUT_TOKENS,
                "temperature": 0.0,
                "stream": False,
            },
            900,
        )
        return result["choices"][0]["message"]["content"].strip()


@dataclass
class SessionReport:
    path: Path
    session_id: str
    action: str = "skip"
    reason: str = ""
    context_tokens: int = 0
    summary_tokens: int = 0
    chunks: int = 0
    backup: str = ""


def discover_sessions(projects_root: Path, idle_minutes: int, now: float) -> list[Path]:
    if not projects_root.is_dir():
        return []
    newest_per_project: dict[Path, float] = {}
    candidates: list[Path] = []
    for path in projects_root.glob("*/*.jsonl"):
        stamp = path.stat().st_mtime
        newest_per_project[path.parent] = max(newest_per_project.get(path.parent, 0.0), stamp)
        if SESSION_FILE.match(path.name):
            candidates.append(path)
    idle_after = now - idle_minutes * 60
    sessions: list[Path] = []
    for path in candidates:
        # The whole session stays skipped while any file of the project is
        # still being written, because sidechains share the project directory.
        if newest_per_project[path.parent] > idle_after:
            continue
        sessions.append(path)
    return sorted(sessions)


def _record_text(record: dict) -> str:
    if record.get("type") not in ("user", "assistant") or record.get("isSidechain"):
        return ""
    message = record.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in ("text", "text_delta"):
            parts.append(str(block.get("text", "")))
        elif kind == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                parts.append("[tool result] " + inner)
            elif isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append("[tool result] " + str(item.get("text", "")))
        elif kind == "tool_use":
            payload = json.dumps(block.get("input", {}), ensure_ascii=False)[:400]
            parts.append(f"[tool call {block.get('name', '?')}] {payload}")
    return "\n".join(parts)


def _is_compact_boundary(record: dict) -> bool:
    return record.get("type") == "system" and record.get("subtype") == "compact_boundary"


def active_records(path: Path) -> tuple[list[dict], dict | None]:
    """Return the records that define the current context (after the last
    compact boundary) plus the last message record for template fields."""
    records: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    start = 0
    for index, record in enumerate(records):
        if _is_compact_boundary(record):
            start = index + 1
    active = records[start:]
    last_message = next((r for r in reversed(active) if r.get("type") in ("user", "assistant")), None)
    if last_message is None:
        last_message = records[-1] if records else None
    return active, last_message


def build_chunks(records: list[dict], chunk_tokens: int) -> list[str]:
    budget = chunk_tokens * CHARS_PER_TOKEN
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for record in records:
        text = _record_text(record)
        if not text:
            continue
        role = record.get("message", {}).get("role", "user") if isinstance(record.get("message"), dict) else "user"
        entry = f"[{role}] {text}"
        if size + len(entry) > budget and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(entry)
        size += len(entry)
    if current:
        chunks.append("\n".join(current))
    return chunks


def last_uuid(path: Path) -> str | None:
    latest: dict | None = None
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("uuid"):
                latest = record
    return latest.get("uuid") if latest else None


def _template_fields(last_message: dict | None) -> dict:
    base = {
        "isSidechain": False,
        "cwd": "",
        "sessionId": "",
        "userType": "external",
        "entrypoint": "cli",
        "version": "",
        "gitBranch": "",
    }
    if isinstance(last_message, dict):
        for key in ("cwd", "sessionId", "version", "gitBranch", "slug", "entrypoint"):
            value = last_message.get(key)
            if isinstance(value, str) and value:
                base[key] = value
    return base


def append_compact(path: Path, summary: str, template: dict, pre_tokens: int,
                   post_tokens: int, duration_ms: int, backup_root: Path) -> str:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{path.stem}.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl"
    shutil.copyfile(path, backup)
    logical = last_uuid(path)
    boundary_uuid = str(uuid.uuid4())
    boundary = {
        "parentUuid": None,
        "logicalParentUuid": logical,
        **template,
        "type": "system",
        "subtype": "compact_boundary",
        "content": "Conversation compacted",
        "level": "info",
        "compactMetadata": {
            "trigger": COMPACT_TRIGGER,
            "preTokens": pre_tokens,
            "postTokens": post_tokens,
            "cumulativeDroppedTokens": max(pre_tokens - post_tokens, 0),
            "durationMs": duration_ms,
        },
        "timestamp": now_iso(),
        "uuid": boundary_uuid,
    }
    summary_record = {
        "parentUuid": boundary_uuid,
        **template,
        "type": "user",
        "message": {"role": "user", "content": SUMMARY_PREFIX + summary},
        "timestamp": now_iso(),
        "uuid": str(uuid.uuid4()),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(boundary, ensure_ascii=False) + "\n")
        stream.write(json.dumps(summary_record, ensure_ascii=False) + "\n")
    return str(backup)


def compact_session(path: Path, client: StrataClient, model: str, window: int,
                    reserve: int, chunk_tokens: int, dry_run: bool,
                    backup_root: Path) -> SessionReport:
    report = SessionReport(path=path, session_id=path.stem)
    active, last_message = active_records(path)
    chunks = build_chunks(active, chunk_tokens)
    if not chunks:
        report.reason = "no conversation records"
        return report
    token_counts = [client.count_tokens(model, chunk) for chunk in chunks]
    estimate = sum(token_counts)
    report.context_tokens = estimate
    limit = window - reserve
    if estimate <= limit:
        report.reason = f"within window ({estimate} <= {limit})"
        return report
    if max(token_counts) > window - SUMMARY_OUTPUT_TOKENS - 4_096:
        # One chunk alone cannot fit: resplit at a smaller token budget.
        smaller = max((window - reserve) // 2, 16_384)
        if smaller >= chunk_tokens:
            report.reason = "cannot fit a chunk under the window"
            return report
        return compact_session(path, client, model, window, reserve, smaller, dry_run, backup_root)
    started = time.monotonic()
    carry = ""
    for index, chunk in enumerate(chunks):
        instruction = FINAL_INSTRUCTION if index == len(chunks) - 1 else CHUNK_INSTRUCTION
        carry = client.summarize(model, carry, chunk, instruction)
        report.chunks += 1
    summary = carry
    report.summary_tokens = client.count_tokens(model, summary)
    if report.summary_tokens > limit:
        report.reason = f"summary still too large ({report.summary_tokens} > {limit})"
        return report
    if dry_run:
        report.action = "would-compact"
        report.reason = "dry run"
        return report
    report.backup = append_compact(
        path, summary, _template_fields(last_message), estimate, report.summary_tokens,
        int((time.monotonic() - started) * 1000), backup_root)
    report.action = "compacted"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--projects-root", type=Path)
    parser.add_argument("--server-url", default=SERVER_URL)
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--session-id", help="compact exactly this session id")
    parser.add_argument("--idle-minutes", type=int, default=DEFAULT_IDLE_MINUTES)
    parser.add_argument("--reserve", type=int, default=DEFAULT_RESERVE_TOKENS,
                        help="tokens left free under the window for the session's next request")
    parser.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--max-sessions", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="report only; this is also safe to rerun")
    parser.add_argument("--apply", action="store_true", help="append compact boundaries (without this, dry-run)")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--receipt", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)

    dry_run = not args.apply
    home = args.home
    projects_root = args.projects_root or home / ".claude" / "projects"
    backup_root = args.backup_dir or home / "AppData" / "Local" / "Strata" / "session-compacts"
    api_key_file = args.api_key_file or home / KEY_FILE
    api_key = api_key_file.read_text(encoding="utf-8").strip() if api_key_file.is_file() else None
    client = StrataClient(args.server_url, api_key)
    try:
        health = client.health()
        if health.get("status") != "ok" or health.get("loaded") is not True:
            print("ERROR: Strata server is not ready for compaction", file=sys.stderr)
            return 1
        window = int(health["max_context"])
        model = str(health["model"])
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        print(f"ERROR: cannot read the Strata server health: {exc}", file=sys.stderr)
        return 1

    if args.session_id:
        matches = sorted(projects_root.glob(f"*/{args.session_id}.jsonl"))
        if not matches:
            print(f"ERROR: session {args.session_id} not found under {projects_root}", file=sys.stderr)
            return 1
        candidates = matches[:1]
    else:
        candidates = [p for p in discover_sessions(projects_root, args.idle_minutes, time.time())
                      if p.stat().st_size > 256_000][: args.max_sessions]

    reports: list[SessionReport] = []
    for path in candidates:
        try:
            reports.append(compact_session(path, client, model, window, args.reserve,
                                           args.chunk_tokens, dry_run, backup_root))
        except (OSError, ValueError, KeyError, urllib.error.URLError, json.JSONDecodeError) as exc:
            report = SessionReport(path=path, session_id=path.stem, action="failed", reason=str(exc)[:300])
            reports.append(report)

    for report in reports:
        if report.action in ("skip",) and report.context_tokens and "within window" in report.reason:
            print(f"skip  {report.session_id}  {report.reason}")
        else:
            print(f"{report.action}  {report.session_id}  context={report.context_tokens} "
                  f"summary={report.summary_tokens} chunks={report.chunks} {report.reason} {report.backup}".rstrip())
    print(f"done  server={window} context, model={model}, sessions examined={len(reports)}")
    payload = {
        "status": "ok",
        "window": window,
        "model": model,
        "dry_run": dry_run,
        "sessions": [
            {key: getattr(report, key) for key in
             ("session_id", "action", "reason", "context_tokens", "summary_tokens", "chunks", "backup")}
            for report in reports
        ],
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
