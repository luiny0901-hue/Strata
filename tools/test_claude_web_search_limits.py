"""Focused tests for long-running SearXNG request pacing."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from tools.claude_mcp.usage_ledger import UsageLedger, UsageLedgerError


class _CancelledDuringWait:
    def __init__(self):
        self.waited = None

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waited = seconds
        return True


class SearXNGRequestPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = UsageLedger(Path(self.temp_dir.name) / "usage.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_count_is_unbounded_when_requests_respect_interval(self):
        # More than the former hourly and daily quotas, spread across an hour.
        for index in range(720):
            self.ledger.reserve_searxng(now=10_000 + index * 5)

    def test_early_request_waits_then_reserves_without_error(self):
        self.ledger.reserve_searxng(now=10_000)
        with patch("tools.claude_mcp.usage_ledger.time.time", side_effect=[10_002, 10_005]), \
                patch("tools.claude_mcp.usage_ledger.time.sleep") as sleep:
            self.ledger.reserve_searxng()
        sleep.assert_has_calls([call(3.0)])

    def test_engine_failure_cooldown_blocks_other_process_then_expires(self):
        with patch('tools.claude_mcp.usage_ledger.time.time', return_value=10_000):
            self.ledger.set_cooldown('searxng', 60, 'search_engine_unavailable')
        other = UsageLedger(self.ledger.path)
        with self.assertRaisesRegex(UsageLedgerError, '요청을 다시 보내지 않았습니다'):
            other.reserve_searxng(now=10_001)
        other.reserve_searxng(now=10_060)

    def test_waiting_request_observes_a_new_engine_failure_cooldown(self):
        self.ledger.reserve_searxng(now=10_000)
        def fail_while_waiting(seconds):
            self.ledger.set_cooldown('searxng', 60, 'search_engine_unavailable')
        with patch('tools.claude_mcp.usage_ledger.time.time', return_value=10_002), \
                patch('tools.claude_mcp.usage_ledger.time.sleep', side_effect=fail_while_waiting):
            with self.assertRaisesRegex(UsageLedgerError, '요청을 다시 보내지 않았습니다'):
                self.ledger.reserve_searxng()

    def test_wait_observes_cancellation_before_reserving(self):
        self.ledger.reserve_searxng(now=10_000)
        cancellation = _CancelledDuringWait()
        with patch("tools.claude_mcp.usage_ledger.time.time", return_value=10_002):
            with self.assertRaisesRegex(UsageLedgerError, "취소"):
                self.ledger.reserve_searxng(cancel_event=cancellation)
        self.assertEqual(cancellation.waited, 3.0)


if __name__ == "__main__":
    unittest.main()
