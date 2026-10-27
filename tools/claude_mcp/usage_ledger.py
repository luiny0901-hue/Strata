"""Persistent, query-free monthly and rate-limit accounting for web search."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import time


class UsageLedgerError(RuntimeError):
    """The local safety ledger could not safely admit a search request."""


def _default_path() -> Path:
    override = os.environ.get("STRATA_WEB_SEARCH_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser() / "usage.sqlite3"
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "Strata" / "WebSearch" / "usage.sqlite3"
    return Path.home() / ".local" / "state" / "strata" / "web-search" / "usage.sqlite3"


def _month(now: float | None = None) -> str:
    moment = datetime.fromtimestamp(now, tz=timezone.utc) if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y-%m")


class UsageLedger:
    """Coordinate quotas across Claude sessions without storing search text."""

    # Keep the local fallback available for long-running agents without a
    # request-count quota. Serialize upstream dispatches with a short interval.
    SEARX_MIN_INTERVAL_SECONDS = 5

    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connection() as connection:
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS monthly_usage (
                        month TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        units INTEGER NOT NULL,
                        requests INTEGER NOT NULL,
                        PRIMARY KEY (month, provider)
                    );
                    CREATE TABLE IF NOT EXISTS exhausted_months (
                        month TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        PRIMARY KEY (month, provider)
                    );
                    CREATE TABLE IF NOT EXISTS provider_cooldowns (
                        provider TEXT PRIMARY KEY,
                        until_epoch INTEGER NOT NULL,
                        reason TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS searxng_requests (
                        occurred_epoch INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_searxng_requests_epoch
                        ON searxng_requests(occurred_epoch);
                """)
            if os.name != "nt":
                os.chmod(self.path.parent, 0o700)
                if self.path.exists():
                    os.chmod(self.path, 0o600)
        except (OSError, sqlite3.Error):
            raise UsageLedgerError("로컬 검색 사용량 장부를 준비하지 못했습니다. 검색을 보내지 않았습니다.") from None

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def reserve_monthly(self, provider: str, units: int, limit: int) -> tuple[bool, int, str | None]:
        """Reserve before dispatch so concurrent sessions cannot exceed local caps."""
        month = _month()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                disabled = connection.execute(
                    "SELECT reason FROM exhausted_months WHERE month=? AND provider=?", (month, provider)
                ).fetchone()
                if disabled:
                    connection.commit()
                    return False, 0, disabled[0]
                current = connection.execute(
                    "SELECT units FROM monthly_usage WHERE month=? AND provider=?", (month, provider)
                ).fetchone()
                used = int(current[0]) if current else 0
                if used + units > limit:
                    connection.commit()
                    return False, used, "local_monthly_cap"
                connection.execute(
                    "INSERT INTO monthly_usage(month,provider,units,requests) VALUES(?,?,?,1) "
                    "ON CONFLICT(month,provider) DO UPDATE SET units=units+excluded.units, requests=requests+1",
                    (month, provider, units),
                )
                connection.commit()
                return True, used + units, None
        except sqlite3.Error:
            raise UsageLedgerError("로컬 검색 사용량 장부를 갱신하지 못했습니다. 검색을 보내지 않았습니다.") from None

    def mark_month_exhausted(self, provider: str, reason: str) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO exhausted_months(month,provider,reason) VALUES(?,?,?) "
                    "ON CONFLICT(month,provider) DO UPDATE SET reason=excluded.reason",
                    (_month(), provider, reason[:80]),
                )
        except sqlite3.Error:
            raise UsageLedgerError("검색 제공자의 월간 사용 중단 상태를 저장하지 못했습니다.") from None

    def set_cooldown(self, provider: str, seconds: int, reason: str) -> None:
        until = int(time.time()) + max(1, seconds)
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO provider_cooldowns(provider,until_epoch,reason) VALUES(?,?,?) "
                    "ON CONFLICT(provider) DO UPDATE SET until_epoch=excluded.until_epoch,reason=excluded.reason",
                    (provider, until, reason[:80]),
                )
        except sqlite3.Error:
            raise UsageLedgerError("검색 제공자의 제한 대기 상태를 저장하지 못했습니다.") from None

    def cooldown(self, provider: str, now: int | None = None) -> tuple[int, str | None]:
        moment = int(time.time()) if now is None else int(now)
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT until_epoch,reason FROM provider_cooldowns WHERE provider=?", (provider,)
                ).fetchone()
                if not row:
                    return 0, None
                remaining = int(row[0]) - moment
                if remaining <= 0:
                    connection.execute("DELETE FROM provider_cooldowns WHERE provider=?", (provider,))
                    return 0, None
                return remaining, str(row[1])
        except sqlite3.Error:
            raise UsageLedgerError("검색 제공자 제한 상태를 읽지 못했습니다.") from None

    def reserve_searxng(self, now: int | float | None = None, cancel_event=None) -> None:
        """Pace requests across sessions without hourly or daily count quotas."""
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise UsageLedgerError("SearXNG 요청 간격을 기다리는 중 검색이 취소되었습니다.")
            moment = time.time() if now is None else float(now)
            wait_seconds = 0
            try:
                with self._connection() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        "DELETE FROM searxng_requests WHERE occurred_epoch < ?",
                        (moment - self.SEARX_MIN_INTERVAL_SECONDS,),
                    )
                    row = connection.execute(
                        "SELECT MAX(occurred_epoch) FROM searxng_requests"
                    ).fetchone()
                    last_request = float(row[0]) if row and row[0] is not None else None
                    if (last_request is not None
                            and moment - last_request < self.SEARX_MIN_INTERVAL_SECONDS):
                        wait_seconds = self.SEARX_MIN_INTERVAL_SECONDS - (moment - last_request)
                        connection.rollback()
                    else:
                        connection.execute("INSERT INTO searxng_requests(occurred_epoch) VALUES(?)", (moment,))
                        connection.commit()
                        return
            except sqlite3.Error:
                raise UsageLedgerError("로컬 검색 간격 장부를 갱신하지 못했습니다. 검색을 보내지 않았습니다.") from None

            # An injected clock is used by deterministic callers; it cannot
            # advance while this method sleeps, so report the remaining delay.
            if now is not None:
                raise UsageLedgerError(f"로컬 검색 간격을 지키기 위해 {wait_seconds}초 기다려야 합니다.")
            if cancel_event is None:
                time.sleep(wait_seconds)
            elif cancel_event.wait(wait_seconds):
                raise UsageLedgerError("SearXNG 요청 간격을 기다리는 중 검색이 취소되었습니다.")
