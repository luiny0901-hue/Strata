"""Isolated setup tests: no IDE, network, model, driver installation or GUI input."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.remote_agent_client import setup_client as client


class RemoteClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "사용자 with spaces"
        self.home.mkdir()
        self.opencode = self.home / "opencode.exe"
        self.driver = self.home / "cua-driver.exe"
        self.node = self.home / "node.exe"
        for path in (self.opencode, self.driver, self.node):
            path.write_bytes(b"fixture")
        self.health = {"status": "ok", "max_context": 262144, "images": True}
        self.model = {"id": "actual-server-id"}

    def tearDown(self):
        self.temp.cleanup()

    def install(self, driver=True):
        with patch.dict("os.environ", {"CUA_NODE_EXE": str(self.node)}), \
             patch.object(client, "secure_windows_directory"):
            return client.write_setup(self.home, "http://100.64.0.10:8080/v1", "fixture-secret",
                                      self.health, self.model, self.opencode, "2.0.22",
                                      self.driver if driver else None, "existing")

    def test_fresh_remote_setup_shares_recovery_and_window_policy(self):
        name = self.install()
        config = json.loads(client.overlay_path(self.home).read_text(encoding="utf-8"))
        self.assertEqual(config["agents"]["build"]["steps"], 60)
        self.assertEqual(config["compaction"]["buffer"], 65536)
        self.assertEqual(config["permissions"][-1], {"action": "*", "resource": "*", "effect": "allow"})
        self.assertEqual(config["providers"]["strata"]["models"]["server"]["modelID"], "actual-server-id")
        self.assertEqual(config["providers"]["strata"]["models"]["server"]["limit"]["output"], 32000)
        server = config["mcp"]["servers"]["cua-driver"]
        self.assertFalse(server["disabled"])
        self.assertFalse(server["codemode"])
        self.assertEqual(server["environment"]["CUA_DRIVER_PERMISSION_MODE"], "standard")
        self.assertTrue(Path(server["command"][1]).is_file())
        self.assertTrue((client.client_dir(self.home) / "cua-driver/opencode-catalog.mjs").is_file())
        self.assertNotIn("fixture-secret", client.overlay_path(self.home).read_text(encoding="utf-8"))
        self.assertEqual(self.install(), name)  # no duplicate synthetic ACP registration
        self.assertEqual(len(json.loads(client.acp_path(self.home).read_text(encoding="utf-8"))["agent_servers"]), 1)

    def test_no_cua_still_installs_recovery_and_terminal_instructions(self):
        self.install(False)
        config = json.loads(client.overlay_path(self.home).read_text(encoding="utf-8"))
        self.assertEqual(len(config["instructions"]), 3)
        self.assertNotIn("cua-driver", config.get("mcp", {}))
        self.assertTrue((client.client_dir(self.home) / "scripts/run_bounded_command.sh").is_file())
        self.assertNotIn(b"\r", (client.client_dir(self.home) / "scripts/run_bounded_command.sh").read_bytes())

    def test_missing_node_is_caught_before_credentials_or_config_are_written(self):
        with patch("tools.configure_opencode_cua_automation._find_runtime_path", side_effect=ValueError("node missing")):
            with self.assertRaisesRegex(client.SetupError, "node missing"):
                self.install()
        self.assertFalse(client.key_path(self.home).exists())
        self.assertFalse(client.overlay_path(self.home).exists())

    def test_small_remote_context_gets_bounded_reserve_and_no_unreported_images(self):
        config = client.build_overlay("http://127.0.0.1:8080/v1", self.model, {"max_context": 8192}, self.home)
        self.assertEqual(config["compaction"]["buffer"], 2048)
        self.assertEqual(config["compaction"]["keep"]["tokens"], 1024)
        self.assertEqual(config["providers"]["strata"]["models"]["server"]["capabilities"]["input"], ["text"])

    def test_doctor_detects_missing_or_modified_installed_policy_assets(self):
        self.install()
        state = json.loads(client.state_path(self.home).read_text(encoding="utf-8"))
        self.assertEqual(client.check_assets(state), [])
        policy = client.client_dir(self.home) / "cua-driver/opencode-policy.mjs"
        policy.write_text("modified", encoding="utf-8")
        self.assertEqual(len(client.check_assets(state)), 1)
        policy.unlink()
        self.assertEqual(len(client.check_assets(state)), 1)

    def test_malformed_existing_ide_config_is_preserved_without_any_setup_writes(self):
        path = client.acp_path(self.home)
        path.parent.mkdir()
        path.write_text("broken", encoding="utf-8")
        with self.assertRaises(client.SetupError):
            self.install()
        self.assertEqual(path.read_text(encoding="utf-8"), "broken")
        self.assertFalse(client.client_dir(self.home).exists())


if __name__ == "__main__":
    unittest.main()
