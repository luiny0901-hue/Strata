from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import claude_desktop_runtime as runtime_module
from tools.claude_desktop_runtime import (
    DesktopRuntime, StreamSummary, accepted_then_finished, canonical_session, dialog_state,
)


CLI_ID = "11111111-2222-4333-8444-555555555555"
OTHER_ID = "aaaaaaaa-1111-4222-8333-bbbbbbbbbbbb"
PROFILE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
DESKTOP_ID = "local_" + CLI_ID
OPERATION = "desktop-fixture-op"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def text_end_turn(text="fixture summary"):
    return {"type": "assistant", "message": {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}]}}


def thinking_end_turn():
    return {"type": "assistant", "message": {"stop_reason": "end_turn",
            "content": [{"type": "thinking", "thinking": "private-thinking-fixture"}]}}


def accepted_result(operation=OPERATION, *, accepted=True, state="queued", is_error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": is_error,
            "content": json.dumps({"operation_id": operation, "accepted": accepted, "state": state})}]}}


class ClockEvent:
    def __init__(self, start=10.0):
        self.now, self.cancelled = start, False

    def is_set(self):
        return self.cancelled

    def wait(self, duration):
        self.now += duration
        return self.cancelled


class FakeWindowsSystem:
    def __init__(self, cli, app):
        self.sid = "fixture-user-sid"
        self.package = {"family": "Claude_fixture", "version": "3.1.0.0", "exe": str(app),
                        "app_id": "Claude_fixture!Claude"}
        self.identities = {pid: {"pid": pid, "started": pid * 100, "sid": self.sid, "exe": str(exe)}
                           for pid, exe in ((100, app), (200, cli), (300, app.parent / "python.exe"))}
        self.processes = {
            100: {"pid": 100, "parent": 1, "exe": str(app), "command": "desktop-fixture"},
            200: {"pid": 200, "parent": 100, "exe": str(cli), "command": f'"{cli}" --session-id {CLI_ID}'},
            300: {"pid": 300, "parent": 200, "exe": str(app.parent / "python.exe"), "command": "mcp-fixture"},
        }
        self.live = set(self.identities)
        self.actions = []

    def discover(self, family=None):
        if family is not None and family != self.package["family"]:
            raise ValueError("fixture package mismatch")
        return deepcopy(self.package)

    def snapshot(self):
        return deepcopy({pid: row for pid, row in self.processes.items() if pid in self.live})

    def main(self, package, snapshot=None):
        if package != self.package:
            raise ValueError("fixture package mismatch")
        return self.identity(100)

    def identity(self, pid):
        if pid not in self.live:
            raise ValueError("fixture process absent")
        return deepcopy(self.identities[pid])

    def matches(self, identity):
        return identity["pid"] in self.live and self.identities[identity["pid"]] == identity

    def quit(self, identity):
        self.actions.append(("quit", identity["pid"]))
        self.live.discard(100)
        self.live.discard(200)

    def launch(self, session_id):
        self.actions.append(("launch", session_id))


class RuntimeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.project = self.home / "project"
        self.project.mkdir(parents=True)
        self.checkpoint = self.project / "checkpoint.md"
        self.checkpoint.write_text("Done: fixture. Remaining: independent verification.\n", encoding="utf-8")
        self.user_data = self.root / "desktop-profile"
        self.cli = self.user_data / "claude-code" / "2.1.334" / "win32-x64" / "claude.exe"
        self.cli.parent.mkdir(parents=True)
        self.cli.write_bytes(b"native-cli-fixture")
        self.app = self.root / "installed-app" / "claude.exe"
        self.app.parent.mkdir()
        self.app.write_bytes(b"desktop-app-fixture")
        self.row = {"sessionId": DESKTOP_ID, "cliSessionId": CLI_ID, "cwd": str(self.project),
                    "model": "claude-fixture-default", "effort": "high", "permissionMode": "bypassPermissions",
                    "cliBinaryPin": {"version": "2.1.334"}, "lastFocusedAt": 10, "isArchived": False}
        self.session_file = self.user_data / "claude-code-sessions" / "account" / "profile" / (DESKTOP_ID + ".json")
        save_json(self.session_file, self.row)
        self.library = self.user_data / "configLibrary"
        save_json(self.library / "_meta.json", {"appliedId": PROFILE_ID})
        self.profile = {"inferenceProvider": "gateway", "inferenceGatewayBaseUrl": "http://127.0.0.1:10100",
                        "inferenceModels": [{"name": "claude-fixture-default", "isFamilyDefault": True}]}
        save_json(self.library / (PROFILE_ID + ".json"), self.profile)
        self.owner_file = self.home / ".claude/strata-opencodex.json"
        self.settings_file = self.home / ".claude/settings.json"
        self.owner = {"base_url": "http://127.0.0.1:10100", "model": "strata/qwen-fixture"}
        self.settings = {"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:10100"},
                         "model": "strata/qwen-fixture"}
        save_json(self.owner_file, self.owner)
        save_json(self.settings_file, self.settings)
        self.transcript = self.home / ".claude/projects/project-fixture" / (CLI_ID + ".jsonl")
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text(json.dumps(text_end_turn()) + "\n", encoding="utf-8")
        self.system = FakeWindowsSystem(self.cli, self.app)
        self.runtime = DesktopRuntime({"version": 1, "enabled": True, "package_family": "Claude_fixture",
                                      "user_data_dir": str(self.user_data)}, home=self.home, system=self.system)
        self.help = patch.object(runtime_module.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, stdout=b"--resume --print --output-format --permission-mode --effort --model --verbose"))
        self.help_mock = self.help.start()
        self.addCleanup(self.help.stop)

    def prepare(self):
        return self.runtime.prepare_binding(CLI_ID, self.checkpoint, 300)

    def update_session(self, **changes):
        self.row.update(changes)
        save_json(self.session_file, self.row)

    def append_events(self, *events):
        with self.transcript.open("a", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event) + "\n")

    def resume_process(self, binding, *, result_session=CLI_ID, output=None, exit_code=0):
        self.system.live.discard(200)
        created = []
        if output is None:
            output = (json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "private-assistant-fixture"}]}}) + "\n" + json.dumps({
                "type": "result", "subtype": "success", "is_error": False,
                "session_id": result_session, "num_turns": 2, "result": "private-result-fixture"}) + "\n").encode()

        class FakeOwnedProcess:
            def __init__(self, command, log, *, cwd=None, environment=None):
                self.command, self.log, self.cwd, self.environment = command, log, cwd, environment
                self.started = False
                self.stopped = []
                self.child = SimpleNamespace(returncode=exit_code)
                created.append(self)

            def start(self):
                self.started = True
                self.log.write(output)

            def alive(self):
                return False

            def stop(self, *, grace_seconds):
                self.stopped.append(grace_seconds)

        return created, patch("tools.strata_server_supervisor.OwnedProcess", FakeOwnedProcess)

    def test_verified_binding_uses_exact_project_model_native_cli_and_saved_modes(self):
        binding = self.prepare()
        self.assertEqual(binding["cli_session_id"], CLI_ID)
        self.assertEqual(binding["desktop_session_id"], DESKTOP_ID)
        self.assertEqual(binding["model"], "strata/qwen-fixture")
        self.assertEqual(binding["permission_mode"], "bypassPermissions")
        self.assertEqual(binding["effort"], "high")
        self.assertEqual(binding["requester_identity"]["pid"], 200)
        self.assertEqual(binding["desktop_identity"]["pid"], 100)
        self.assertEqual(self.system.actions, [])
        self.assertEqual(self.help_mock.call_args.args[0], [str(self.cli.resolve()), "--help"])

    def test_session_uuid_must_be_exact_and_lowercase(self):
        for value in (None, "not-a-session", OTHER_ID.upper(), "{" + CLI_ID + "}"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_session(value)
        self.assertEqual(canonical_session(CLI_ID), CLI_ID)

    def test_sdk_fresh_session_uses_hook_binding_not_latest_saved_session(self):
        self.system.processes[200]['command'] = 'claude --input-format stream-json --await-initialize'
        event = {'session_id': CLI_ID, 'cwd': str(self.project)}
        self.runtime.record_session_start(event, 300)
        self.assertEqual(self.runtime.current_session_id(300), CLI_ID)
        self.assertEqual(self.prepare()['requester_identity']['pid'], 200)

    def test_sdk_binding_rejects_pid_reuse_and_session_mismatch(self):
        self.system.processes[200]['command'] = 'claude --await-initialize'
        self.runtime.record_session_start({'session_id': OTHER_ID, 'cwd': str(self.project)}, 300)
        with self.assertRaises(ValueError):
            self.prepare()
        self.system.identities[200]['started'] += 1
        with self.assertRaises((OSError, ValueError)):
            self.runtime.current_session_id(300)

    def test_sdk_binding_requires_the_original_desktop_birth(self):
        self.system.processes[200]['command'] = 'claude --await-initialize'
        self.runtime.record_session_start({'session_id': CLI_ID, 'cwd': str(self.project)}, 300)
        self.system.identities[100]['started'] += 1
        with self.assertRaises(ValueError):
            self.runtime.current_session_id(300)

    def test_manual_desktop_reopen_prevents_a_second_writer(self):
        binding = self.prepare()
        self.system.live.discard(200)
        self.update_session(lastFocusedAt=11)
        created, process_patch = self.resume_process(binding)
        with process_patch, self.assertRaisesRegex(ValueError, 'reopened'):
            self.runtime.continue_session(binding, OPERATION, 'c'*32, ClockEvent(), time.monotonic()+10)
        self.assertEqual(created, [])

    def test_owned_restore_helper_drains_result_before_parsing(self):
        helper = self.root/'client/tools/claude_desktop_restore.py'
        helper.parent.mkdir(parents=True)
        helper.write_text('import json; print(json.dumps({"state":"focused"}), flush=True)\n')
        self.runtime.config.update(client_root=str(helper.parents[1]), client_python=sys.executable)
        binding = self.prepare()
        self.runtime._restore_cua(binding, self.system.identity(100), time.monotonic()+10)

    def test_checkpoint_cannot_escape_the_session_project(self):
        outside = self.root / "outside.md"
        outside.write_text("fixture checkpoint", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside"):
            self.runtime.prepare_binding(CLI_ID, outside, 300)
        self.assertEqual(self.system.actions, [])

    def test_checkpoint_symlink_is_rejected(self):
        symlink = self.project / "checkpoint-symlink.md"
        try:
            symlink.symlink_to(self.checkpoint)
        except OSError as exc:
            self.skipTest("Temporary fixture symlinks are unavailable: " + type(exc).__name__)
        with self.assertRaises(ValueError):
            self.runtime.prepare_binding(CLI_ID, symlink, 300)
        self.assertEqual(self.system.actions, [])

    def test_checkpoint_hardlink_is_rejected(self):
        hardlink = self.project / "checkpoint-hardlink.md"
        os.link(self.checkpoint, hardlink)
        with self.assertRaises(ValueError):
            self.runtime.prepare_binding(CLI_ID, hardlink, 300)
        self.assertEqual(self.system.actions, [])

    def test_changed_checkpoint_is_rejected_before_quit_and_before_resume(self):
        binding = self.prepare()
        self.checkpoint.write_text("changed checkpoint", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Checkpoint changed"):
            self.runtime.quit(binding)
        created, process_patch = self.resume_process(binding)
        with process_patch, self.assertRaisesRegex(ValueError, "Checkpoint changed"):
            self.runtime.continue_session(binding, OPERATION, "0" * 32, ClockEvent(), float("inf"))
        self.assertEqual(created, [])
        self.assertEqual(self.system.actions, [])

    def test_duplicate_session_across_profile_inventory_is_rejected(self):
        duplicate = self.user_data / "claude-code-sessions/other-account/other-profile" / (DESKTOP_ID + ".json")
        save_json(duplicate, self.row)
        with self.assertRaisesRegex(ValueError, "uniquely"):
            self.prepare()

    def test_duplicate_transcript_is_rejected(self):
        duplicate = self.home / ".claude/projects/another-project" / (CLI_ID + ".jsonl")
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.prepare()

    def test_wrong_model_or_gateway_profile_is_rejected(self):
        cases = [
            {"inferenceGatewayBaseUrl": "http://127.0.0.1:9999"},
            {"inferenceProvider": "anthropic"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                save_json(self.library / (PROFILE_ID + ".json"), {**self.profile, **changes})
                with self.assertRaisesRegex(ValueError, "current Strata default"):
                    self.prepare()
        save_json(self.library / (PROFILE_ID + ".json"), self.profile)
        self.update_session(model="unrelated-model")
        with self.assertRaisesRegex(ValueError, "current Strata default"):
            self.prepare()

    def test_nonlocal_gateway_route_is_rejected(self):
        save_json(self.owner_file, {**self.owner, "base_url": "http://127.0.0.1:9999"})
        save_json(self.settings_file, {**self.settings, "env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:9999"}})
        with self.assertRaisesRegex(ValueError, "local OpenCodex"):
            self.prepare()

    def test_common_route_owner_and_settings_must_match(self):
        cases = [
            {**self.settings, "model": "strata/other-model"},
            {**self.settings, "env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:9999"}},
        ]
        for settings in cases:
            with self.subTest(settings_field="model" if settings["model"] != self.owner["model"] else "base_url"):
                save_json(self.settings_file, settings)
                with self.assertRaisesRegex(ValueError, "Common Claude route changed"):
                    self.prepare()

    def test_permission_and_effort_modes_are_preserved_without_escalation(self):
        for permission in ("default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk"):
            with self.subTest(permission=permission):
                self.update_session(permissionMode=permission)
                self.assertEqual(self.prepare()["permission_mode"], permission)
        for effort in (None, "low", "medium", "high"):
            with self.subTest(effort=effort):
                self.update_session(effort=effort)
                self.assertEqual(self.prepare()["effort"], effort)
        self.update_session(permissionMode="unsupported")
        with self.assertRaisesRegex(ValueError, "permission"):
            self.prepare()

    def test_unrelated_caller_ancestry_is_rejected(self):
        self.system.processes[300]["parent"] = 999
        with self.assertRaisesRegex(ValueError, "requested from"):
            self.prepare()

    def test_matching_native_cli_outside_desktop_ancestry_is_rejected(self):
        self.system.processes[200]["parent"] = 999
        with self.assertRaises(ValueError):
            self.prepare()

    def test_wrong_user_on_native_requester_ancestor_is_rejected(self):
        self.system.identities[200]["sid"] = "different-fixture-user"
        with self.assertRaises(ValueError):
            self.prepare()

    def test_wrong_session_in_calling_cli_arguments_is_rejected(self):
        self.system.processes[200]["command"] = f'"{self.cli}" --resume {OTHER_ID}'
        with self.assertRaisesRegex(ValueError, "requested session"):
            self.prepare()

    def test_thinking_end_turn_after_acceptance_does_not_finish_handoff(self):
        binding = self.prepare()
        binding["operation_id"] = OPERATION
        self.append_events(accepted_result(), thinking_end_turn())
        event = ClockEvent()
        with patch.object(runtime_module.time, "monotonic", side_effect=lambda: event.now), \
                self.assertRaisesRegex(ValueError, "did not finish"):
            self.runtime.wait_for_handoff(binding, event, event.now + 1.5)
        self.assertEqual(self.system.actions, [])

    def test_accepted_result_followed_by_text_end_turn_allows_handoff(self):
        binding = self.prepare()
        binding["operation_id"] = OPERATION
        self.append_events(accepted_result(), text_end_turn())
        event = ClockEvent()
        with patch.object(runtime_module.time, "monotonic", side_effect=lambda: event.now):
            self.runtime.wait_for_handoff(binding, event, event.now + 2)
        self.assertGreaterEqual(event.now, 11)
        self.assertEqual(self.system.actions, [])

    def test_failed_or_nonaccepted_tool_result_does_not_authorize_restart(self):
        for result in (accepted_result(accepted=False, state="failed", is_error=True),
                       accepted_result(accepted=False),
                       accepted_result(is_error=True),
                       accepted_result(operation=OPERATION + "-different")):
            with self.subTest(result_kind=result["message"]["content"][0]["is_error"]):
                self.assertFalse(accepted_then_finished([result, text_end_turn()], OPERATION))

    def test_text_end_turn_must_follow_the_accepted_result(self):
        self.assertFalse(accepted_then_finished([text_end_turn(), accepted_result()], OPERATION))
        self.assertEqual(dialog_state([thinking_end_turn()]), "busy")

    def test_structured_mcp_accepted_result_is_supported_but_empty_final_text_is_not_idle(self):
        event = accepted_result()
        content = event["message"]["content"][0]["content"]
        event["message"]["content"][0]["content"] = [{"type": "text", "text": content}]
        self.assertTrue(accepted_then_finished([event, text_end_turn()], OPERATION))
        self.assertFalse(accepted_then_finished([event, text_end_turn("")], OPERATION))

    def test_other_pending_desktop_session_prevents_handoff(self):
        binding = self.prepare()
        binding["operation_id"] = OPERATION
        self.append_events(accepted_result(), text_end_turn())
        other = self.transcript.parent / (OTHER_ID + ".jsonl")
        other.write_text(json.dumps({"type": "user", "message": {"content": "pending-fixture"}}) + "\n", encoding="utf-8")
        self.system.processes[201] = {"pid": 201, "parent": 100, "exe": str(self.cli),
                                      "command": f'"{self.cli}" --session-id {OTHER_ID}'}
        self.system.identities[201] = {"pid": 201, "started": 20100, "sid": self.system.sid, "exe": str(self.cli)}
        self.system.live.add(201)
        self.assertFalse(self.runtime._other_sessions_idle(binding))
        event = ClockEvent()
        with patch.object(runtime_module.time, "monotonic", side_effect=lambda: event.now), self.assertRaises(ValueError):
            self.runtime.wait_for_handoff(binding, event, event.now + 1.5)
        self.assertEqual(self.system.actions, [])

    def test_native_resume_preserves_settings_scrubs_environment_and_returns_only_metadata(self):
        binding = self.prepare()
        created, process_patch = self.resume_process(binding)
        env = {"ANTHROPIC_API_KEY": "private-key-fixture", "ANTHROPIC_BASE_URL": "private-url-fixture",
               "CLAUDE_CODE_SESSION_ID": "private-session-fixture", "STRATA_CUA_TASK_STATE": "private-state-fixture",
               "USER_OPTION": "keep-fixture"}
        with process_patch, patch.dict(os.environ, env):
            result = self.runtime.continue_session(binding, OPERATION, "0" * 32, ClockEvent(), float("inf"))
        self.assertEqual(len(created), 1)
        process = created[0]
        self.assertTrue(process.started)
        self.assertEqual(process.stopped, [2])
        self.assertEqual(process.cwd, str(self.project.resolve()))
        for flag, expected in (("--resume", CLI_ID), ("--model", "strata/qwen-fixture"),
                               ("--permission-mode", "bypassPermissions"), ("--effort", "high")):
            self.assertEqual(process.command[process.command.index(flag) + 1], expected)
        self.assertEqual(process.environment["USER_OPTION"], "keep-fixture")
        for name in env:
            if name != "USER_OPTION":
                self.assertNotIn(name, process.environment)
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(result["subtype"], "success")
        self.assertFalse(result["is_error"])

    def test_native_resume_rejects_result_from_a_different_session(self):
        binding = self.prepare()
        created, process_patch = self.resume_process(binding, result_session=OTHER_ID)
        with process_patch, self.assertRaisesRegex(ValueError, "original session identity"):
            self.runtime.continue_session(binding, OPERATION, "0" * 32, ClockEvent(), float("inf"))
        self.assertEqual(created[0].stopped, [2])

    def test_cancelled_recovery_does_not_start_a_native_cli(self):
        binding = self.prepare()
        created, process_patch = self.resume_process(binding)
        event = ClockEvent(); event.cancelled = True
        with process_patch, self.assertRaises(ValueError):
            self.runtime.continue_session(binding, OPERATION, "0" * 32, event, float("inf"))
        self.assertFalse(any(process.started for process in created))

    def test_expired_recovery_deadline_does_not_start_a_native_cli(self):
        binding = self.prepare()
        created, process_patch = self.resume_process(binding)
        with process_patch, patch.object(runtime_module.time, "monotonic", return_value=20), self.assertRaises(ValueError):
            self.runtime.continue_session(binding, OPERATION, "0" * 32, ClockEvent(), 19)
        self.assertFalse(any(process.started for process in created))


class StreamSummaryTests(unittest.TestCase):
    @staticmethod
    def result_line(**extra):
        row = {"type": "result", "subtype": "success", "is_error": False,
               "session_id": CLI_ID, "num_turns": 1, **extra}
        return json.dumps(row).encode() + b"\n"

    def test_private_content_and_tool_payloads_are_not_retained_in_result(self):
        rows = [
            {"type": "assistant", "message": {"content": "private-assistant-fixture"}},
            {"type": "tool_result", "content": "private-tool-fixture"},
        ]
        body = b"".join(json.dumps(row).encode() + b"\n" for row in rows) + self.result_line(
            result="private-result-fixture", prompt="private-prompt-fixture", stderr="private-error-fixture")
        summary = StreamSummary()
        for offset in range(0, len(body), 17):
            summary.write(body[offset:offset + 17])
        summary.finish()
        self.assertEqual(summary.result, {"subtype": "success", "is_error": False,
                                         "session_id": CLI_ID, "num_turns": 1})
        self.assertNotIn("private", json.dumps(summary.result))
        self.assertEqual(summary.pending, bytearray())
        self.assertEqual(summary.bytes, len(body))

    def test_oversized_complete_event_is_flagged_and_not_interpreted_as_result(self):
        summary = StreamSummary()
        with patch.object(runtime_module, "MAX_TRANSCRIPT_TAIL", 256):
            summary.write(self.result_line(result="private" * 100))
            summary.finish()
        self.assertTrue(summary.oversized)
        self.assertIsNone(summary.result)

    def test_oversized_fragmented_line_discards_its_tail_until_newline(self):
        summary = StreamSummary()
        with patch.object(runtime_module, "MAX_TRANSCRIPT_TAIL", 256):
            summary.write(b"x" * 257)
            summary.write(self.result_line())
            summary.finish()
            self.assertTrue(summary.oversized)
            self.assertIsNone(summary.result)
            summary.write(self.result_line())
            summary.finish()
        self.assertEqual(summary.result["session_id"], CLI_ID)


if __name__ == "__main__":
    unittest.main()
