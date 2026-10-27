import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools.claude_desktop_restart import DesktopRestartController


def publish(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.controller = None
        self.wait_entered = threading.Event()
        self.wait_release = threading.Event()
        self.wait_release.set()
        self.quit_entered = threading.Event()
        self.quit_release = threading.Event()
        self.quit_release.set()
        self.continue_entered = threading.Event()
        self.continue_release = threading.Event()
        self.continue_release.set()
        self.ack = True
        self.reopen_error = False
        self.quit_error = False
        self.nonce = None
        self.result = {"exit_code": 0, "subtype": "success", "is_error": False,
                       "duration_ms": 12.4, "result": "private-response-fixture"}
        self.after_wait = None

    def prepare_binding(self, session_id, checkpoint_path, caller_pid):
        self.calls.append("prepare")
        return {"session_id": session_id, "checkpoint_path": checkpoint_path,
                "caller_pid": caller_pid, "private_fixture": "private-binding-fixture"}

    @staticmethod
    def wait_release_or_cancel(release, event):
        while not release.wait(0.01):
            if event.is_set():
                return

    def wait_for_handoff(self, binding, event, deadline):
        self.calls.append("wait")
        self.wait_entered.set()
        self.wait_release_or_cancel(self.wait_release, event)
        if self.after_wait:
            self.after_wait()

    def quit(self, binding):
        self.calls.append("quit")
        self.quit_entered.set()
        self.quit_release.wait(3)
        if self.quit_error:
            raise RuntimeError("private-runtime-error-fixture")

    def continue_session(self, binding, operation_id, nonce, event, deadline):
        self.calls.append("continue")
        self.nonce = nonce
        self.continue_entered.set()
        self.wait_release_or_cancel(self.continue_release, event)
        if self.ack and not event.is_set():
            self.controller.acknowledge(operation_id, nonce, binding["session_id"])
        return dict(self.result)

    def reopen(self, binding):
        self.calls.append("reopen")
        if self.reopen_error:
            raise RuntimeError("private-reopen-error-fixture")


class DesktopRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.checkpoint = self.root / "checkpoint.md"
        self.checkpoint.write_text("Completed: probe. Remaining: verification.\n", encoding="utf-8")
        self.runtime = FakeRuntime()
        self.controller = DesktopRestartController(self.root, self.runtime, publish_fn=publish)
        self.runtime.controller = self.controller

    def tearDown(self):
        self.runtime.wait_release.set()
        self.runtime.quit_release.set()
        self.runtime.continue_release.set()
        self.controller.close()
        self.temp.cleanup()

    def prepare(self, operation="one", **options):
        return self.controller.prepare(operation, "session-1", self.checkpoint, os.getpid(), **options)

    def settle(self):
        self.controller.worker.join(timeout=3)
        self.assertFalse(self.controller.worker.is_alive())

    def test_success_is_handoff_completion_and_status_does_not_expose_nonce_or_binding(self):
        first = self.prepare()
        self.assertEqual(first["state"], "queued")
        self.assertTrue(first["accepted"])
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "ready")
        self.assertTrue(status["handoff_completed"])
        self.assertEqual(status["task_completion"], "not_asserted")
        self.assertEqual(self.runtime.calls, ["prepare", "wait", "quit", "continue", "reopen"])
        encoded = json.dumps(status)
        for private in (self.runtime.nonce, "private-binding-fixture", "private-response-fixture"):
            self.assertNotIn(private, encoded)
        self.assertNotIn("binding", status)
        self.assertNotIn("nonce", status)

    def test_same_operation_is_not_repeated_and_different_request_is_rejected(self):
        self.prepare()
        self.settle()
        before = list(self.runtime.calls)
        again = self.controller.prepare("one", "session-1", self.checkpoint, os.getpid() + 100)
        self.assertEqual(again["state"], "ready")
        for session, path, timeout in (("other-session", self.checkpoint, 86400),
                                       ("session-1", self.root / "other.md", 86400),
                                       ("session-1", self.checkpoint, 10)):
            with self.subTest(session=session, path=path, timeout=timeout), self.assertRaises(ValueError):
                self.controller.prepare("one", session, path, os.getpid(), timeout)
        self.assertEqual(self.runtime.calls, before)

    def test_old_completed_operation_is_preserved_after_another_operation(self):
        self.prepare("one")
        self.settle()
        self.prepare("two")
        self.settle()
        calls = list(self.runtime.calls)
        self.assertEqual(self.prepare("one")["state"], "ready")
        self.assertEqual(self.runtime.calls, calls)

    def test_only_one_active_desktop_transaction_is_allowed(self):
        self.runtime.wait_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.wait_entered.wait(2))
        with self.assertRaises(ValueError):
            self.prepare("another")
        self.assertEqual(self.runtime.calls.count("prepare"), 1)
        self.controller.cancel("one")
        self.settle()

    def test_cancellation_tombstone_survives_owner_restart_and_overtakes_prepare(self):
        self.assertEqual(self.controller.cancel("cancelled-first")["state"], "cancelled")
        self.controller.close()
        restored = DesktopRestartController(self.root, self.runtime, publish_fn=publish)
        try:
            with self.assertRaisesRegex(ValueError, "cancelled"):
                restored.prepare("cancelled-first", "session-1", self.checkpoint, os.getpid())
            self.assertEqual(restored.status("cancelled-first")["state"], "cancelled")
            self.assertEqual(self.runtime.calls, [])
        finally:
            restored.close()

    def test_cancel_before_quit_does_not_touch_the_app(self):
        self.runtime.wait_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.wait_entered.wait(2))
        self.controller.cancel("one")
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "cancelled")
        self.assertNotIn("quit", self.runtime.calls)
        self.assertNotIn("continue", self.runtime.calls)
        self.assertNotIn("reopen", self.runtime.calls)

    def test_cancel_after_quit_only_restores_app_without_continuation(self):
        self.runtime.quit_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.quit_entered.wait(2))
        self.controller.cancel("one")
        self.runtime.quit_release.set()
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "cancelled")
        self.assertEqual(self.runtime.calls.count("quit"), 1)
        self.assertEqual(self.runtime.calls.count("reopen"), 1)
        self.assertNotIn("continue", self.runtime.calls)

    def test_cancel_during_continuation_is_passed_to_runtime_and_app_is_reopened(self):
        self.runtime.continue_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.continue_entered.wait(2))
        self.controller.cancel("one")
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "cancelled")
        self.assertEqual(self.runtime.calls.count("continue"), 1)
        self.assertEqual(self.runtime.calls.count("reopen"), 1)

    def test_initial_persistence_failure_prevents_worker_and_app_actions(self):
        def fail(path, value):
            raise OSError("fixture full disk")
        self.controller.close()
        self.controller = DesktopRestartController(self.root, self.runtime, publish_fn=fail)
        self.runtime.controller = self.controller
        with self.assertRaises(OSError):
            self.prepare()
        self.assertIsNone(self.controller.worker)
        self.assertEqual(self.runtime.calls, ["prepare"])

    def test_persistence_failure_before_quit_prevents_app_shutdown(self):
        def fail_before_quit(path, value):
            if value.get("state") == "quitting":
                raise OSError("fixture full disk")
            publish(path, value)
        self.controller.close()
        self.controller = DesktopRestartController(self.root, self.runtime, publish_fn=fail_before_quit)
        self.runtime.controller = self.controller
        self.prepare()
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["error_code"], "receipt_persistence_failed")
        self.assertFalse(status["handoff_completed"])
        self.assertNotIn("quit", self.runtime.calls)
        with self.assertRaises(ValueError):
            self.prepare("next")

    def test_successful_cli_without_acknowledgement_is_not_ready(self):
        self.runtime.ack = False
        self.prepare()
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["error_code"], "resume_acknowledgement_missing")
        self.assertFalse(status["handoff_completed"])
        self.assertEqual(self.runtime.calls.count("reopen"), 1)

    def test_terminal_receipt_persistence_failure_does_not_report_ready(self):
        def fail_ready(path, value):
            if value.get("state") == "ready":
                raise OSError("fixture full disk")
            publish(path, value)
        self.controller.close()
        self.controller = DesktopRestartController(self.root, self.runtime, publish_fn=fail_ready)
        self.runtime.controller = self.controller
        self.prepare()
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertFalse(status["handoff_completed"])
        self.assertFalse(status["persistence_confirmed"])
        self.assertEqual(self.runtime.calls.count("reopen"), 1)

    def test_acknowledgement_requires_the_exact_nonce_and_session(self):
        self.runtime.ack = False
        self.runtime.continue_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.continue_entered.wait(2))
        for nonce, session in (("0" * 32, "session-1"), (self.runtime.nonce, "other-session")):
            with self.subTest(session=session), self.assertRaises(ValueError):
                self.controller.acknowledge("one", nonce, session)
        self.controller.acknowledge("one", self.runtime.nonce, "session-1")
        self.runtime.continue_release.set()
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "ready")

    def test_nonzero_cli_or_error_result_never_reports_ready(self):
        self.runtime.result = {"exit_code": 7, "subtype": "error_during_execution", "is_error": True}
        self.prepare()
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "failed")
        self.assertFalse(status["handoff_completed"])
        self.assertEqual(status["continuation_result"]["exit_code"], 7)
        self.assertEqual(self.runtime.calls.count("reopen"), 1)

    def test_zero_exit_without_explicit_success_fields_never_reports_ready(self):
        cases = [
            {"exit_code": 0, "subtype": "success"},
            {"exit_code": 0, "is_error": False},
            {"exit_code": 0, "is_error": False, "subtype": "unknown"},
            {"exit_code": 0, "is_error": True, "subtype": "success"},
        ]
        for index, result in enumerate(cases):
            with self.subTest(result=result):
                self.runtime.result = result
                operation = "unverified-" + str(index)
                self.prepare(operation)
                self.settle()
                status = self.controller.status(operation)
                self.assertEqual(status["state"], "failed")
                self.assertFalse(status["handoff_completed"])

    def test_reopen_failure_is_not_hidden_by_successful_continuation(self):
        self.runtime.reopen_error = True
        self.prepare()
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["error_code"], "reopen_failed")
        self.assertFalse(status["handoff_completed"])
        self.assertNotIn("private-reopen-error-fixture", json.dumps(status))

    def test_uncertain_quit_is_not_retried_and_recovery_is_attempted_once(self):
        self.runtime.quit_error = True
        self.prepare()
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "needs_attention")
        self.assertEqual(self.runtime.calls.count("quit"), 1)
        self.assertEqual(self.runtime.calls.count("reopen"), 1)
        self.assertNotIn("continue", self.runtime.calls)
        self.prepare()
        self.assertEqual(self.runtime.calls.count("quit"), 1)

    def test_owner_restart_marks_interrupted_receipt_without_replaying(self):
        self.prepare()
        self.settle()
        self.controller.close()
        receipt_path = next(self.controller.directory.glob("*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["state"] = "continuing"
        publish(receipt_path, receipt)
        runtime = FakeRuntime()
        restored = DesktopRestartController(self.root, runtime, publish_fn=publish)
        try:
            status = restored.prepare("one", "session-1", self.checkpoint, os.getpid())
            self.assertEqual(status["state"], "needs_attention")
            self.assertEqual(status["error_code"], "owner_interrupted")
            self.assertFalse(status["handoff_completed"])
            self.assertEqual(runtime.calls, [])
        finally:
            restored.close()

    def test_owner_restart_rejects_a_ready_receipt_without_successful_continuation(self):
        self.prepare()
        self.settle()
        self.controller.close()
        receipt_path = next(self.controller.directory.glob("*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        cases = [
            {"exit_code": 7, "is_error": False, "subtype": "success"},
            {"exit_code": 0, "subtype": "success"},
            {"exit_code": 0, "is_error": False},
            {"exit_code": 0, "is_error": False, "subtype": "unknown"},
        ]
        for result in cases:
            with self.subTest(result=result):
                receipt["continuation_result"] = result
                publish(receipt_path, receipt)
                restored = DesktopRestartController(self.root, FakeRuntime(), publish_fn=publish)
                try:
                    status = restored.status("one")
                    self.assertEqual(status["state"], "needs_attention")
                    self.assertEqual(status["error_code"], "invalid_completion_receipt")
                    self.assertFalse(status["handoff_completed"])
                finally:
                    restored.close()

    def test_close_waits_for_cancelled_quit_and_app_recovery(self):
        self.runtime.quit_release.clear()
        self.prepare()
        self.assertTrue(self.runtime.quit_entered.wait(2))
        release = threading.Timer(0.03, self.runtime.quit_release.set)
        release.start()
        try:
            self.controller.close(timeout_seconds=1)
        finally:
            release.join(timeout=1)
        self.assertFalse(self.controller.worker.is_alive())
        self.assertEqual(self.controller.status("one")["state"], "cancelled")
        self.assertEqual(self.runtime.calls.count("reopen"), 1)
        self.assertNotIn("continue", self.runtime.calls)

    def test_close_timeout_raises_and_preserves_attention_even_after_late_recovery(self):
        reopen_entered, reopen_release = threading.Event(), threading.Event()
        def blocked_reopen(binding):
            self.runtime.calls.append("reopen")
            reopen_entered.set()
            reopen_release.wait(3)
        self.runtime.reopen = blocked_reopen
        self.prepare()
        self.assertTrue(reopen_entered.wait(2))
        try:
            with self.assertRaisesRegex(RuntimeError, "did not settle"):
                self.controller.close(timeout_seconds=0.01)
            status = self.controller.status("one")
            self.assertEqual(status["state"], "needs_attention")
            self.assertEqual(status["error_code"], "owner_shutdown_timeout")
            self.assertFalse(status["handoff_completed"])
        finally:
            reopen_release.set()
            self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["error_code"], "owner_shutdown_timeout")
        self.assertFalse(status["handoff_completed"])

    def test_deadline_reached_before_quit_does_not_touch_app(self):
        now = [0.0]
        self.controller.close()
        self.controller = DesktopRestartController(self.root, self.runtime, publish_fn=publish, clock=lambda: now[0])
        self.runtime.controller = self.controller
        self.runtime.after_wait = lambda: now.__setitem__(0, 2.0)
        self.prepare(continuation_timeout_seconds=1)
        self.settle()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["error_code"], "deadline_exceeded")
        self.assertNotIn("quit", self.runtime.calls)

    def test_external_controller_survives_caller_stdio_eof(self):
        caller = subprocess.Popen([sys.executable, "-u", "-c", "import sys; print('ready',flush=True); sys.stdin.buffer.read()"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: caller.poll() is None and caller.kill())
        self.assertEqual(caller.stdout.readline().strip(), b"ready")

        def wait_for_caller_exit(binding, event, deadline):
            self.runtime.calls.append("wait")
            self.runtime.wait_entered.set()
            while caller.poll() is None and not event.wait(0.01):
                if time.monotonic() >= deadline:
                    raise TimeoutError()
        self.runtime.wait_for_handoff = wait_for_caller_exit
        self.controller.prepare("one", "session-1", self.checkpoint, caller.pid, 5)
        self.assertTrue(self.runtime.wait_entered.wait(2))
        caller.stdin.close()
        caller.wait(timeout=3)
        caller.stdout.close()
        self.settle()
        self.assertEqual(self.controller.status("one")["state"], "ready")
        self.assertEqual(self.runtime.calls.count("continue"), 1)

    def test_worker_start_failure_is_durable_and_does_not_change_app(self):
        with patch("tools.claude_desktop_restart.threading.Thread.start", side_effect=RuntimeError("fixture")):
            with self.assertRaises(ValueError):
                self.prepare()
        status = self.controller.status("one")
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["error_code"], "worker_start_failed")
        self.assertNotIn("quit", self.runtime.calls)


if __name__ == "__main__":
    unittest.main()
