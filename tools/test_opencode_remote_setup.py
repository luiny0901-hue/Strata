"""Checks the secret-free Windows and macOS OpenCode import templates."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MODEL = "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs"
KEY_FILE = "{file:~/.config/strata/STRATA_API_KEY}"
HOST_URL = "http://STRATA_HOST_LAN_IP:8080/v1"


class RemoteOpenCodeTemplateTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads((ROOT / "docs" / name).read_text(encoding="utf-8"))

    def test_windows_and_macos_templates_keep_shared_model_and_local_cua(self) -> None:
        for name, shell in (
            ("opencode-remote-windows.example.jsonc", "pwsh"),
            ("opencode-remote-macos.example.jsonc", "/bin/zsh"),
        ):
            with self.subTest(name=name):
                document = self.load(name)
                provider = document["providers"]["strata"]
                self.assertEqual(document["model"], EXPECTED_MODEL)
                self.assertEqual(document["shell"], shell)
                self.assertEqual(provider["settings"]["baseURL"], HOST_URL)
                self.assertEqual(provider["settings"]["apiKey"], KEY_FILE)
                self.assertEqual(document["compaction"]["keep"]["tokens"], 12000)
                self.assertEqual(document["compaction"]["buffer"], 65536)
                self.assertEqual(document["agents"]["build"]["steps"], 60)
                self.assertEqual(
                    document["mcp"]["servers"]["cua-driver"]["command"],
                    ["cua-driver", "mcp"],
                )
                self.assertNotIn("C:\\", json.dumps(document))
                self.assertNotIn("REPLACE_LOCALLY", json.dumps(document))

    def test_provider_fragment_has_no_embedded_secret(self) -> None:
        document = self.load("opencode-strata-provider.example.json")
        settings = document["providers"]["strata"]["settings"]
        self.assertEqual(settings["baseURL"], HOST_URL)
        self.assertEqual(settings["apiKey"], KEY_FILE)

    def test_windows_lan_gate_is_fail_closed_and_scopes_known_rules(self) -> None:
        checker = (ROOT / "tools/windows/check_strata_lan_firewall.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "tools/windows/allow_strata_lan.ps1").read_text(encoding="utf-8")
        self.assertIn("StrataOpenCodeLan8080", checker)
        self.assertIn("StrataOpenCodeNotPrivate8080", checker)
        self.assertIn("LocalSubnet", checker)
        self.assertIn("No server was started", checker)
        self.assertIn("llama-server-8080", installer)
        self.assertIn("llama.cpp API 8080 LAN", installer)
        self.assertIn("Set-NetFirewallRule", installer)
        self.assertNotIn("Remove-NetFirewallRule", installer)

    def test_setup_guide_uses_official_cua_driver_installers(self) -> None:
        guide = (ROOT / "docs/REMOTE_WINDOWS_MAC_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("https://cua.ai/driver/install.ps1", guide)
        self.assertIn("https://cua.ai/driver/install.sh", guide)
        self.assertNotIn("https://cua.ai/install.ps1", guide)


if __name__ == "__main__":
    unittest.main(verbosity=2)
