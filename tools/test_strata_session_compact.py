"""CPU-only tests for the switch-time session compactor."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strata_session_compact import (
    SUMMARY_PREFIX,
    active_records,
    build_chunks,
    compact_session,
    discover_sessions,
    main,
    now_iso,
)


def message_record(index: int, role: str, text: str, parent: str | None, session: str) -> dict:
    return {
        "parentUuid": parent,
        "isSidechain": False,
        "type": role,
        "message": {"role": role, "content": text},
        "sessionId": session,
        "cwd": "C:/tmp/project",
        "version": "9.9.9",
        "gitBranch": "feature/x",
        "timestamp": now_iso(),
        "uuid": f"{index:08d}-0000-4000-8000-000000000000",
    }


def write_session(directory: Path, session: str, records: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


class FakeClient:
    def __init__(self, window: int = 100_000, model: str = "test-model") -> None:
        self.window = window
        self.model = model
        self.summarize_calls: list[tuple[str, str]] = []

    def health(self) -> dict:
        return {"status": "ok", "loaded": True, "max_context": self.window, "model": self.model}

    def count_tokens(self, model: str, text: str) -> int:
        return max(1, len(text) // 4)

    def summarize(self, model: str, carry_over: str, excerpt: str, instruction: str) -> str:
        self.summarize_calls.append((carry_over, instruction))
        return "SECTIONED SUMMARY " + ("detail " * 40)


class SessionFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_session(self, session: str, count: int, size: int = 2_000) -> Path:
        records = []
        parent = None
        for index in range(count):
            role = "user" if index % 2 == 0 else "assistant"
            record = message_record(index, role, f"message {index}: " + "x" * size, parent, session)
            records.append(record)
            parent = record["uuid"]
        return write_session(self.projects / "project", session, records)

    def test_oversized_session_gets_boundary_and_summary_appended(self) -> None:
        path = self.make_session("11111111-1111-4111-8111-111111111111", 200)
        before = path.read_bytes()
        client = FakeClient()
        backup_root = self.root / "backups"
        report = compact_session(path, client, client.model, client.window, 49_152, 4_000, False, backup_root)
        self.assertEqual(report.action, "compacted")
        self.assertGreater(report.context_tokens, client.window - 49_152)
        self.assertGreaterEqual(len(client.summarize_calls), 2)
        self.assertTrue(client.summarize_calls[1][0], "the later chunk must carry the earlier summary")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), len(before.decode("utf-8").splitlines()) + 1)
        boundary = json.loads(lines[-2])
        summary = json.loads(lines[-1])
        self.assertEqual(boundary["subtype"], "compact_boundary")
        self.assertIsNone(boundary["parentUuid"])
        self.assertEqual(boundary["logicalParentUuid"], "00000199-0000-4000-8000-000000000000")
        self.assertEqual(boundary["compactMetadata"]["trigger"], "manual")
        self.assertGreater(boundary["compactMetadata"]["preTokens"], boundary["compactMetadata"]["postTokens"])
        self.assertEqual(boundary["sessionId"], summary["sessionId"])
        self.assertEqual(boundary["cwd"], "C:/tmp/project")
        self.assertEqual(summary["parentUuid"], boundary["uuid"])
        self.assertEqual(summary["type"], "user")
        self.assertTrue(summary["message"]["content"].startswith(SUMMARY_PREFIX))
        self.assertTrue(Path(report.backup).is_file())
        self.assertEqual(Path(report.backup).read_bytes(), before)

    def test_within_window_session_is_left_untouched(self) -> None:
        path = self.make_session("22222222-2222-4222-8222-222222222222", 4, size=100)
        before = path.read_bytes()
        client = FakeClient()
        report = compact_session(path, client, client.model, client.window, 49_152, 4_000, False, self.root / "b")
        self.assertEqual(report.action, "skip")
        self.assertIn("within window", report.reason)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(client.summarize_calls, [])

    def test_dry_run_appends_nothing(self) -> None:
        path = self.make_session("33333333-3333-4333-8333-333333333333", 200)
        before = path.read_bytes()
        client = FakeClient()
        report = compact_session(path, client, client.model, client.window, 49_152, 4_000, True, self.root / "b")
        self.assertEqual(report.action, "would-compact")
        self.assertEqual(path.read_bytes(), before)

    def test_recent_compact_boundary_limits_the_active_context(self) -> None:
        path = self.make_session("44444444-4444-4444-8444-444444444444", 400)
        boundary = {"parentUuid": None, "type": "system", "subtype": "compact_boundary", "uuid": "b" * 8 + "-0000-4000-8000-000000000000"}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(boundary) + "\n")
        active, _ = active_records(path)
        self.assertEqual(active, [])
        client = FakeClient()
        report = compact_session(path, client, client.model, client.window, 49_152, 4_000, False, self.root / "b")
        self.assertEqual(report.action, "skip")
        self.assertIn("no conversation records", report.reason)

    def test_giant_single_message_reports_cannot_fit(self) -> None:
        path = self.make_session("55555555-5555-4555-8555-555555555555", 1, size=700_000)
        client = FakeClient()
        report = compact_session(path, client, client.model, client.window, 49_152, 4_000, False, self.root / "b")
        self.assertEqual(report.action, "skip")
        self.assertIn("cannot fit", report.reason)

    def test_active_project_directories_are_skipped_by_mtime(self) -> None:
        path = self.make_session("66666666-6666-4666-8666-666666666666", 10)
        now = time.time()
        os.utime(path, (now - 86_400, now - 86_400))
        idle_dir = path.parent
        self.assertIn(path, discover_sessions(self.projects, 60, now))
        (idle_dir / "other.jsonl").write_text("{}", encoding="utf-8")
        self.assertEqual(discover_sessions(self.projects, 60, now), [])


class ExtractionTests(unittest.TestCase):
    def test_record_text_covers_tool_blocks_and_ignores_other_records(self) -> None:
        from tools.strata_session_compact import _record_text

        record = {
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}},
            ]},
        }
        text = _record_text(record)
        self.assertIn("hello", text)
        self.assertIn("[tool call Read]", text)
        self.assertIn("a.py", text)
        tool_result = {
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "content": [{"type": "text", "text": "output"}]},
            ]},
        }
        self.assertIn("[tool result] output", _record_text(tool_result))
        self.assertEqual(_record_text({"type": "system", "subtype": "compact_boundary"}), "")
        self.assertEqual(_record_text({"type": "user", "isSidechain": True, "message": {"role": "user", "content": "side"}}), "")

    def test_chunks_preserve_order_and_stay_bounded(self) -> None:
        records = [message_record(index, "user", f"m{index}-" + "y" * 5_000, None, "s") for index in range(30)]
        chunks = build_chunks(records, 4_000)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4_000 * 4 + 6_000)
        self.assertIn("m0-", chunks[0])
        self.assertIn("m29-", chunks[-1])
        joined = "\n".join(chunks)
        self.assertLess(joined.index("m0-"), joined.index("m29-"))


class MainTests(unittest.TestCase):
    def test_main_dry_run_writes_receipt_without_touching_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            projects = home / ".claude" / "projects"
            directory = projects / "project"
            directory.mkdir(parents=True)
            records = []
            parent = None
            for index in range(200):
                record = message_record(index, "user" if index % 2 == 0 else "assistant",
                                        "text " + "z" * 2_000, parent, "77777777-7777-4777-8777-777777777777")
                records.append(record)
                parent = record["uuid"]
            path = write_session(directory, "77777777-7777-4777-8777-777777777777", records)
            os.utime(path, (time.time() - 86_400, time.time() - 86_400))
            (home / ".config" / "strata").mkdir(parents=True)
            (home / ".config" / "strata" / "STRATA_API_KEY").write_text("secret", encoding="utf-8")
            receipt = home / "receipt.json"
            with mock.patch("tools.strata_session_compact.StrataClient", lambda *a, **k: FakeClient()):
                exit_code = main(["--home", str(home), "--dry-run", "--receipt", str(receipt), "--chunk-tokens", "4000"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["sessions"][0]["action"], "would-compact")
            self.assertIn("\n", path.read_text(encoding="utf-8"))
            self.assertNotIn("compact_boundary", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
