"""CPU-only tests for the OpenCode long-session recovery installer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.configure_opencode_session_recovery import DEFAULT_SOURCE, UAC_DENY_POLICIES, apply_config  # noqa: E402


SOURCE = DEFAULT_SOURCE


class InstallerTests(unittest.TestCase):
    def test_applies_recovery_values_and_preserves_existing_provider_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "opencode.json"
            config_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://opencode.ai/config.json",
                        "model": "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs",
                        "providers": {
                            "strata": {
                                "apiKey": "test-secret-preserved",
                                "models": {
                                    "qwen3.8-flash-next-unsloth-ud-iq4_xs": {
                                        "limit": {"context": 262144, "output": 32000}
                                    }
                                },
                            }
                        },
                        "instructions": ["~/custom/EXISTING.md"],
                        "agents": {"build": {"steps": 100}},
                        "compaction": {"auto": False, "keep": {"tokens": 20000}, "buffer": 32768},
                    }
                ),
                encoding="utf-8",
            )
            result = apply_config(config_path, SOURCE)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(config["compaction"]["auto"])
            self.assertEqual(config["compaction"]["keep"]["tokens"], 12000)
            self.assertEqual(config["compaction"]["buffer"], 65536)
            self.assertEqual(config["agents"]["build"]["steps"], 60)
            self.assertEqual(config["policies"], list(UAC_DENY_POLICIES))
            self.assertEqual(config["model"], "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs")
            self.assertEqual(config["providers"]["strata"]["apiKey"], "test-secret-preserved")
            self.assertEqual(
                config["providers"]["strata"]["models"]["qwen3.8-flash-next-unsloth-ud-iq4_xs"]["limit"],
                {"context": 262144, "output": 32000},
            )
            self.assertIn("~/custom/EXISTING.md", config["instructions"])
            self.assertEqual(len(config["instructions"]), 2)
            self.assertEqual(
                Path(result["instructions_path"]).read_text(encoding="utf-8"),
                SOURCE.read_text(encoding="utf-8").rstrip() + "\n",
            )
            self.assertTrue(result["config_backup"])
            self.assertTrue(Path(result["config_backup"]).is_file())

    def test_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            first = apply_config(config_path, SOURCE)
            first_bytes = config_path.read_bytes()
            second = apply_config(config_path, SOURCE)

            self.assertTrue(first["config_changed"])
            self.assertFalse(second["config_changed"])
            self.assertFalse(second["instructions_changed"])
            self.assertEqual(config_path.read_bytes(), first_bytes)
            config = json.loads(first_bytes)
            self.assertEqual(len(config["instructions"]), 1)
            self.assertTrue(config["instructions"][0].endswith("/STRATA_SESSION_RECOVERY_KO.md"))
            self.assertEqual(config["policies"], list(UAC_DENY_POLICIES))

    def test_existing_policies_are_preserved_and_uac_denies_are_last(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            custom = {"action": "tool.use", "resource": "shell:git status *", "effect": "allow"}
            config_path.write_text(json.dumps({"policies": [custom]}), encoding="utf-8")

            apply_config(config_path, SOURCE)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["policies"], [custom, *UAC_DENY_POLICIES])

    def test_malformed_policies_are_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = json.dumps({"policies": {"not": "a list"}}).encode("utf-8")
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "policies must be an array"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)

    def test_installed_recovery_instructions_define_uac_and_completion_boundaries(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("BLOCKED_UAC", source)
        self.assertIn("완료는 종료 상태", source)

    def test_malformed_config_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = b'{"broken":'
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "unreadable JSON"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)
            self.assertFalse((Path(temp) / "STRATA_SESSION_RECOVERY_KO.md").exists())

    def test_invalid_instructions_value_is_refused_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = json.dumps({"instructions": [3]}).encode("utf-8")
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "array of strings"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)
            self.assertFalse((Path(temp) / "STRATA_SESSION_RECOVERY_KO.md").exists())

    def test_existing_instruction_file_is_backed_up_before_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "opencode.json"
            target = root / "STRATA_SESSION_RECOVERY_KO.md"
            target.write_text("user-owned file\n", encoding="utf-8")

            result = apply_config(config_path, SOURCE)

            self.assertTrue(result["instructions_backup"])
            self.assertEqual(Path(result["instructions_backup"]).read_text(encoding="utf-8"), "user-owned file\n")
            self.assertEqual(target.read_text(encoding="utf-8"), SOURCE.read_text(encoding="utf-8").rstrip() + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
