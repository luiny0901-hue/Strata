"""REA integration tests use subprocess fixtures only; no package install occurs."""
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.remote_agent_client import rea_integration as rea


class ReaIntegrationTests(unittest.TestCase):
    def test_published_node_version_policy(self):
        for version in ("v22.19.0", "v24.11.0", "v24.19.0", "v26.0.0"):
            self.assertTrue(rea.supported_node_version(version))
        for version in ("v22.18.0", "v23.0.0", "v24.10.9", "v25.0.0", "not-a-version"):
            self.assertFalse(rea.supported_node_version(version))

    def test_setup_command_pins_package_and_limits_scope_to_opencode(self):
        self.assertEqual(
            rea.rea_setup_command("npx"),
            ["npx", "-y", "rea-agents@6.7.0", "setup", "--yes", "--client", "opencode"],
        )

    def test_configure_uses_official_setup_after_runtime_check(self):
        completed = [
            subprocess.CompletedProcess(["node", "--version"], 0, "v24.19.0\n", ""),
            subprocess.CompletedProcess(["npx"], 0, "configured", ""),
        ]
        with patch.object(rea.shutil, "which", side_effect=lambda name: name), \
             patch.object(rea.subprocess, "run", side_effect=completed) as run, \
             patch.object(rea, "apply_tool_scope", return_value=True) as scope:
            result = rea.configure_opencode()
        self.assertEqual(result.output, "configured")
        self.assertEqual(run.call_args_list[1].args[0], rea.rea_setup_command("npx"))
        scope.assert_called_once()

    def test_failed_setup_preserves_failure_for_caller(self):
        completed = [
            subprocess.CompletedProcess(["node", "--version"], 0, "v24.19.0\n", ""),
            subprocess.CompletedProcess(["npx"], 1, "", "setup failed"),
        ]
        with patch.object(rea.shutil, "which", side_effect=lambda name: name), \
             patch.object(rea.subprocess, "run", side_effect=completed), \
             patch.object(rea, "apply_tool_scope"):
            with self.assertRaisesRegex(rea.ReaSetupError, "setup failed"):
                rea.configure_opencode()

    def test_tool_scope_disables_rea_globally_and_enables_only_rea_subagent(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "opencode.json"
            config.write_text(json.dumps({"mcp": {"rea": {"type": "local"}}}), encoding="utf-8")
            self.assertTrue(rea.apply_tool_scope(config))
            configured = json.loads(config.read_text(encoding="utf-8"))
            self.assertFalse(configured["tools"]["rea_*"])
            self.assertEqual(configured["agent"]["rea_analysis"], rea.REA_AGENT)
            self.assertFalse(rea.apply_tool_scope(config))

    def test_tool_scope_migrates_the_previous_rea_agent_definition(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "opencode.json"
            config.write_text(
                json.dumps({"tools": {"rea_*": False}, "agent": {"rea_analysis": rea.LEGACY_REA_AGENT}}),
                encoding="utf-8",
            )
            self.assertTrue(rea.apply_tool_scope(config))
            configured = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(configured["agent"]["rea_analysis"], rea.REA_AGENT)

    def test_tool_scope_verifier_rejects_missing_scoped_agent(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "opencode.json"
            config.write_text(json.dumps({"tools": {"rea_*": False}}), encoding="utf-8")
            with self.assertRaisesRegex(rea.ReaSetupError, "subagent"):
                rea.verify_tool_scope(config)

    def test_tool_scope_preserves_conflicting_agent_definition(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "opencode.json"
            config.write_text(json.dumps({"agent": {"rea_analysis": {"description": "user-owned"}}}), encoding="utf-8")
            with self.assertRaisesRegex(rea.ReaSetupError, "rea_analysis"):
                rea.apply_tool_scope(config)

    def test_setup_client_preserves_strata_setup_when_rea_declined_or_fails(self):
        from tools.remote_agent_client import setup_client

        with patch("builtins.input", return_value="n"):
            self.assertEqual(setup_client.ensure_rea(), "declined")
        with patch("builtins.input", return_value=""), \
             patch.object(setup_client, "configure_rea_opencode", side_effect=rea.ReaSetupError("network down")):
            self.assertEqual(setup_client.ensure_rea(), "setup-failed")


if __name__ == "__main__":
    unittest.main()
