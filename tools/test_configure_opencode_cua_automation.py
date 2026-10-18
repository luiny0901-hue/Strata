"""CPU-only tests for the persistent OpenCode CUA policy installer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.configure_opencode_cua_automation import (  # noqa: E402
    NEW_DELIVERY_LINE,
    NEW_DISCOVERY_LINE,
    NEW_IDENTITY_LINE,
    NEW_STOP_LINE,
    NEW_STABILITY_LINE,
    OLD_DELIVERY_PREFIX,
    OLD_DISCOVERY_PREFIX,
    OLD_IDENTITY_PREFIX,
    OLD_STOP_PREFIX,
    OLD_STABILITY_PREFIX,
    apply_configuration,
)


OLD_GUI_RULES = (
    "## OpenCode GUI 자동 사용\n"
    f"{OLD_DISCOVERY_PREFIX} PID와 HWND가 일치하는 정확한 창만 `get_window_state`로 확인한다.\n"
    "- 화면 확인 규칙은 보존한다.\n"
    f'{OLD_DELIVERY_PREFIX}"background"`만 사용한다. 기존 창 지정 규칙을 보존한다.\n'
    f"{OLD_STOP_PREFIX} 전경 입력은 재시도하지 않는다.\n"
    f"{OLD_IDENTITY_PREFIX} 실제 결과를 확인한다. 필요한 작업이 끝나면 에이전트 커서를 비활성화한다.\n"
    f"{OLD_STABILITY_PREFIX} `element_token`만 사용한다. 입력 뒤 전체 상태를 즉시 다시 읽는다.\n"
    "- GUI 조작 후 결과를 확인한다.\n"
)


class CuaInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        (self.repo / "docs").mkdir(parents=True)
        (self.repo / "tools" / "cua-driver").mkdir(parents=True)
        for name in ("opencode-mcp.mjs", "opencode-policy.mjs", "opencode-window-scoped.rego"):
            (self.repo / "tools" / "cua-driver" / name).write_text(f"template {name}\n", encoding="utf-8")
        (self.repo / "docs" / "OPENCODE_CUA_AUTOMATION_KO.md").write_text("CUA instructions\n", encoding="utf-8")
        self.config = self.root / "opencode.json"
        self.cua_dir = self.root / "cua-driver"
        self.korean = self.root / "KOREAN_INSTRUCTIONS.md"
        self.node = self.root / "node.exe"
        self.driver = self.root / "cua-driver.exe"
        self.node.write_bytes(b"node")
        self.driver.write_bytes(b"driver")

    def tearDown(self):
        self.temp.cleanup()

    def _seed_config(self):
        self.config.write_text(
            json.dumps(
                {
                    "model": "strata/model",
                    "providers": {"strata": {"apiKey": "sentinel-secret", "models": {"model": {"limit": {"context": 262144, "output": 32000}}}}},
                    "instructions": ["~/custom.md"],
                    "mcp": {
                        "github": {"type": "remote", "url": "https://example.invalid/mcp"},
                        "servers": {
                            "cua-driver": {
                                "type": "local",
                                "command": ["old-node", "old-wrapper"],
                                "environment": {"CUA_DRIVER_EXE": "old-driver", "OTHER": "keep"},
                                "codemode": False,
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.korean.write_text(OLD_GUI_RULES, encoding="utf-8")

    def test_installs_foreground_escalation_and_preserves_other_settings(self):
        self._seed_config()
        wrapper = self.cua_dir / "opencode-mcp.mjs"
        policy = self.cua_dir / "opencode-background-only.rego"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("old wrapper\n", encoding="utf-8")
        policy.write_text("old policy\n", encoding="utf-8")

        result = apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        config = json.loads(self.config.read_text(encoding="utf-8"))
        server = config["mcp"]["cua-driver"]
        self.assertEqual(server["command"], [str(self.node.resolve()), str(wrapper.resolve())])
        self.assertEqual(server["environment"]["CUA_DRIVER_EXE"], str(self.driver.resolve()))
        self.assertEqual(server["environment"]["CUA_DRIVER_POLICY_FILE"], str((self.cua_dir / "opencode-window-scoped.rego").resolve()))
        self.assertEqual(server["environment"]["CUA_DRIVER_PERMISSION_MODE"], "standard")
        self.assertEqual(server["environment"]["OTHER"], "keep")
        self.assertTrue(server["enabled"])
        self.assertNotIn("disabled", server)
        self.assertEqual(config["mcp"]["github"], {"type": "remote", "url": "https://example.invalid/mcp"})
        self.assertNotIn("servers", config["mcp"])
        self.assertEqual(config["model"], "strata/model")
        self.assertEqual(config["providers"]["strata"]["apiKey"], "sentinel-secret")
        self.assertEqual(config["providers"]["strata"]["models"]["model"]["limit"], {"context": 262144, "output": 32000})
        self.assertIn("~/custom.md", config["instructions"])
        self.assertIn("OPENCODE_CUA_AUTOMATION_KO.md", config["instructions"][-1])

        patched = self.korean.read_text(encoding="utf-8")
        self.assertIn(NEW_DISCOVERY_LINE, patched)
        self.assertIn(NEW_DELIVERY_LINE, patched)
        self.assertIn(NEW_STOP_LINE, patched)
        self.assertIn(NEW_IDENTITY_LINE, patched)
        self.assertIn(NEW_STABILITY_LINE, patched)
        self.assertIn("- 화면 확인 규칙은 보존한다.", patched)
        self.assertIn("- GUI 조작 후 결과를 확인한다.", patched)
        self.assertTrue(any(Path(path).name.startswith("opencode-mcp.mjs.before-cua-automation-") for path in result["backups"]))
        self.assertTrue(any(Path(path).name.startswith("KOREAN_INSTRUCTIONS.md.before-cua-automation-") for path in result["backups"]))
        self.assertTrue(any(Path(path).name.startswith("opencode.json.before-cua-automation-") for path in result["backups"]))
        self.assertEqual(wrapper.read_text(encoding="utf-8"), "template opencode-mcp.mjs\n")

    def test_second_run_is_idempotent(self):
        self._seed_config()
        first = apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)
        config_bytes = self.config.read_bytes()
        korean_bytes = self.korean.read_bytes()
        second = apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        self.assertTrue(first["changed_files"])
        self.assertEqual(second["changed_files"], [])
        self.assertEqual(second["backups"], [])
        self.assertEqual(config_bytes, self.config.read_bytes())
        self.assertEqual(korean_bytes, self.korean.read_bytes())

    def test_upgrades_a_mixed_old_and_new_instruction_block(self):
        self._seed_config()
        mixed_rules = OLD_GUI_RULES.replace(
            f'{OLD_DELIVERY_PREFIX}"background"`만 사용한다. 기존 창 지정 규칙을 보존한다.',
            NEW_DELIVERY_LINE,
        ).replace(
            f"{OLD_STOP_PREFIX} 전경 입력은 재시도하지 않는다.",
            NEW_STOP_LINE,
        )
        self.korean.write_text(mixed_rules, encoding="utf-8")

        result = apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        patched = self.korean.read_text(encoding="utf-8")
        for line in (NEW_DISCOVERY_LINE, NEW_DELIVERY_LINE, NEW_STOP_LINE, NEW_IDENTITY_LINE, NEW_STABILITY_LINE):
            self.assertIn(line, patched)
        self.assertTrue(any(Path(path).name.startswith("KOREAN_INSTRUCTIONS.md.before-cua-automation-") for path in result["backups"]))

    def test_unknown_existing_gui_policy_is_refused_without_changes(self):
        self._seed_config()
        self.korean.write_text("## OpenCode GUI 자동 사용\n- A custom policy that needs review.\n", encoding="utf-8")
        config_bytes = self.config.read_bytes()
        korean_bytes = self.korean.read_bytes()

        with self.assertRaisesRegex(ValueError, "Could not safely identify"):
            apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        self.assertEqual(config_bytes, self.config.read_bytes())
        self.assertEqual(korean_bytes, self.korean.read_bytes())
        self.assertFalse(self.cua_dir.exists())

    def test_conflicting_direct_and_legacy_server_entries_are_refused(self):
        self._seed_config()
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["mcp"]["cua-driver"] = {"type": "local", "command": ["different"]}
        self.config.write_text(json.dumps(config), encoding="utf-8")
        config_bytes = self.config.read_bytes()
        korean_bytes = self.korean.read_bytes()

        with self.assertRaisesRegex(ValueError, "Conflicting mcp.cua-driver"):
            apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        self.assertEqual(config_bytes, self.config.read_bytes())
        self.assertEqual(korean_bytes, self.korean.read_bytes())
        self.assertFalse(self.cua_dir.exists())

    def test_malformed_config_is_refused_before_any_change(self):
        self.config.write_bytes(b'{"broken":')
        self.korean.write_text(OLD_GUI_RULES, encoding="utf-8")
        original = self.config.read_bytes()

        with self.assertRaisesRegex(ValueError, "unreadable JSON"):
            apply_configuration(self.config, self.cua_dir, self.korean, self.node, self.driver, self.repo)

        self.assertEqual(original, self.config.read_bytes())
        self.assertEqual(OLD_GUI_RULES, self.korean.read_text(encoding="utf-8"))
        self.assertFalse(self.cua_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
