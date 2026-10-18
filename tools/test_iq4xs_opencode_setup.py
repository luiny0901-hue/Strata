"""CPU-only tests for the portable UD-IQ4_XS setup helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from iq4xs_opencode_setup import (
    MODEL_ID,
    MODEL_KEY,
    MODEL_REVISION,
    SHARD_NAMES,
    apply_opencode_default,
    configure_opencode_document,
    install_terminal_runners,
    render_profile,
    validate_templates,
    verify_assets,
)


ROOT = Path(__file__).resolve().parents[1]


class LauncherImageBudgetTests(unittest.TestCase):
    def test_both_uncensored_modes_use_the_1024_image_token_budget(self) -> None:
        for mode in ("off", "on"):
            with self.subTest(mode=mode):
                launcher = (
                    ROOT / f"run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-{mode}.bat"
                )
                contents = launcher.read_text(encoding="utf-8")
                self.assertEqual(contents.count("--image-max-tokens 1024"), 1)
                self.assertEqual(contents.count("--image-max-tokens"), 1)
                self.assertIn(f"render-profile --mode {mode}", contents)
                self.assertIn("Vision encoding uses CPU.", contents)
                self.assertIn("check_strata_lan_firewall.ps1", contents)
                self.assertIn("exit /b 25", contents)
                self.assertIn(
                    "The comparison sent no image.",
                    contents,
                )


class ProfileTemplateTests(unittest.TestCase):
    def test_templates_declare_matching_on_and_off_contracts(self) -> None:
        self.assertEqual(
            validate_templates(ROOT),
            [
                "PASS template=on uncensored=true context=262144",
                "PASS template=off uncensored=false context=262144",
            ],
        )

    def test_rendered_profiles_use_requested_roots_and_resolve_all_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            strata_root = base / "Strata Root"
            data_root = base / "Strata Data"
            for mode, expected in (("on", True), ("off", False)):
                output = base / f"{mode}.json"
                render_profile(ROOT, mode, strata_root, data_root, output)
                profile = json.loads(output.read_text(encoding="utf-8"))
                self.assertIs(profile["uncensored"], expected)
                self.assertEqual(profile["port"], 8080)
                self.assertEqual(profile["gpu"], 1)
                self.assertEqual(profile["model_name"], MODEL_KEY)
                self.assertEqual(
                    profile["args"][profile["args"].index("--pack") + 1],
                    str(data_root / "packs" / "unsloth-ud-iq4_xs"),
                )
                self.assertEqual(profile["args"][profile["args"].index("--max-context") + 1], "262144")
                self.assertIn("--ple-gguf", profile["args"])
                self.assertTrue(profile["args"][profile["args"].index("--native") + 1].endswith("-00001-of-00003.gguf"))
                self.assertTrue(profile["args"][profile["args"].index("--ple-gguf") + 1].endswith("-00002-of-00003.gguf"))
                self.assertEqual(profile["vision"]["gpu"], False)
                self.assertIn(str(strata_root), profile["exe"])
                self.assertIn(str(data_root), profile["args"][1])
                self.assertNotIn("@", output.read_text(encoding="utf-8"))


class OpenCodeConfigTests(unittest.TestCase):
    def _fixture(self) -> dict:
        return {
            "$schema": "https://opencode.ai/config.json",
            "model": "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs",
            "default_agent": "build",
            "agents": {"build": {"steps": 20}},
            "providers": {
                "strata": {
                    "name": "Strata",
                    "package": "@ai-sdk/openai-compatible",
                    "settings": {
                        "baseURL": "http://127.0.0.1:8080/v1",
                        "apiKey": "test-only-secret",
                    },
                    "models": {"existing-model": {"name": "preserve me"}},
                }
            },
            "instructions": ["Korean"],
        }

    def test_update_preserves_provider_key_and_other_settings(self) -> None:
        config = self._fixture()
        self.assertTrue(configure_opencode_document(config, shell="pwsh"))
        self.assertEqual(config["model"], MODEL_ID)
        self.assertEqual(config["shell"], "pwsh")
        self.assertEqual(config["providers"]["strata"]["settings"]["apiKey"], "test-only-secret")
        self.assertEqual(config["providers"]["strata"]["models"]["existing-model"]["name"], "preserve me")
        self.assertEqual(config["agents"], {"build": {"steps": 20}})
        self.assertEqual(config["instructions"], ["Korean"])
        self.assertEqual(config["providers"]["strata"]["models"][MODEL_KEY]["limit"]["context"], 262144)
        self.assertEqual(config["providers"]["strata"]["models"][MODEL_KEY]["limit"]["output"], 32000)
        self.assertEqual(config["providers"]["strata"]["models"][MODEL_KEY]["capabilities"]["input"], ["text", "image"])

    def test_config_update_is_idempotent(self) -> None:
        config = self._fixture()
        self.assertTrue(configure_opencode_document(config, shell="pwsh"))
        self.assertFalse(configure_opencode_document(config, shell="pwsh"))

    def test_wrong_provider_url_is_rejected_without_mutating_document(self) -> None:
        config = self._fixture()
        config["providers"]["strata"]["settings"]["baseURL"] = "https://example.invalid/v1"
        original = json.loads(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "baseURL"):
            configure_opencode_document(config)
        self.assertEqual(config, original)

    def test_file_update_writes_one_backup_then_becomes_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "opencode.json"
            original = self._fixture()
            config_path.write_text(json.dumps(original), encoding="utf-8")
            changed, backup = apply_opencode_default(config_path)
            self.assertTrue(changed)
            self.assertIsNotNone(backup)
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), original)
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["model"], MODEL_ID)
            changed_again, backup_again = apply_opencode_default(config_path)
            self.assertFalse(changed_again)
            self.assertIsNone(backup_again)
            self.assertEqual(len(list(Path(temporary).glob("*.bak"))), 1)

    def test_install_terminal_runners_is_repeatable_and_preserves_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config_directory = base / "opencode"
            scripts = config_directory / "scripts"
            scripts.mkdir(parents=True)
            neighbor = scripts / "my-custom-script.ps1"
            neighbor.write_text("custom", encoding="utf-8")

            first = install_terminal_runners(ROOT, config_directory)
            self.assertEqual(len([item for item in first if item.startswith("INSTALLED ")]), 2)
            for name in ("run_bounded_command.ps1", "run_bounded_command.sh"):
                self.assertEqual(
                    (scripts / name).read_bytes(),
                    (ROOT / "tools" / "opencode" / name).read_bytes(),
                )
            self.assertEqual(neighbor.read_text(encoding="utf-8"), "custom")

            second = install_terminal_runners(ROOT, config_directory)
            self.assertEqual(len([item for item in second if item.startswith("UNCHANGED ")]), 2)
            self.assertFalse(list(scripts.glob("*.bak")))


class AssetManifestTests(unittest.TestCase):
    def test_manifest_hashes_are_well_formed_and_reference_known_roots(self) -> None:
        manifest = json.loads(
            (ROOT / "docs/reports/2026-10-17-iq4xs-artifact-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["model"]["revision"],
            MODEL_REVISION,
        )
        self.assertGreaterEqual(len(manifest["files"]), 10)
        model_shards = {
            artifact["path"] for artifact in manifest["files"] if artifact["root"] == "model"
        }
        self.assertEqual(model_shards, set(SHARD_NAMES))
        for artifact in manifest["files"]:
            self.assertIn(artifact["root"], ("data", "model", "pack", "fork", "strata"))
            self.assertGreater(artifact["size"], 0)
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")

    def test_verify_assets_reports_missing_files_without_network_or_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            passed, results = verify_assets(ROOT, temp_root / "data", temp_root / "fork")
            self.assertFalse(passed)
            self.assertTrue(results)
            self.assertTrue(any(line.startswith("FAIL missing ") for line in results))
            self.assertTrue(all(line.startswith(("FAIL missing ", "PASS ")) for line in results))

    def test_verify_assets_accepts_matching_fixture_hashes(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            pack_root = temp_root / "data" / "packs" / "unsloth-ud-iq4_xs"
            pack_root.mkdir(parents=True)
            content = b"isolated iq4xs verification fixture"
            artifact = pack_root / "fixture.bin"
            artifact.write_bytes(content)
            manifest_dir = temp_root / "docs" / "reports"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "model": {"revision": MODEL_REVISION},
                "files": [
                    {
                        "root": "pack",
                        "path": "fixture.bin",
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ]
            }
            (manifest_dir / "2026-10-17-iq4xs-artifact-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            passed, results = verify_assets(
                temp_root,
                temp_root / "data",
                temp_root / "fork",
            )
            self.assertTrue(passed)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].startswith("PASS pack/fixture.bin"))

    def test_verify_assets_rejects_a_wrong_hash(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            pack_root = temp_root / "data" / "packs" / "unsloth-ud-iq4_xs"
            pack_root.mkdir(parents=True)
            artifact = pack_root / "fixture.bin"
            artifact.write_bytes(b"changed after manifest")
            manifest_dir = temp_root / "docs" / "reports"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "model": {"revision": MODEL_REVISION},
                "files": [
                    {
                        "root": "pack",
                        "path": "fixture.bin",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(b"original file").hexdigest(),
                    }
                ],
            }
            (manifest_dir / "2026-10-17-iq4xs-artifact-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            passed, results = verify_assets(
                temp_root,
                temp_root / "data",
                temp_root / "fork",
            )
            self.assertFalse(passed)
            self.assertTrue(results[0].startswith("FAIL sha256 pack/fixture.bin"))

    def test_launchers_bind_iq4xs_and_the_requested_uncensor_mode(self) -> None:
        for mode, enabled in (("on", "true"), ("off", "false")):
            path = ROOT / f"run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-{mode}.bat"
            content = path.read_text(encoding="utf-8-sig").lower()
            self.assertIn("unsloth-ud-iq4_xs", content)
            self.assertIn(f"--mode {mode}", content)
            self.assertIn(f"uncensored mode is {mode.upper()}".lower(), content)
            self.assertIn("qwen-nvfp4-gptq-uncensored.gguf", content)
            self.assertIn("port 8080 is occupied", content)
            self.assertIn("no process was stopped", content)
            self.assertNotRegex(content, r"taskkill|stop-process")
            self.assertNotIn("q4_k_xl", content)
            self.assertIn("check_strata_lan_firewall.ps1", content)
            self.assertIn("exit /b 25", content)
            template = ROOT / f"profiles/strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-{mode}.json.template"
            profile = json.loads(template.read_text(encoding="utf-8"))
            self.assertIs(profile["uncensored"], mode == "on")


if __name__ == "__main__":
    unittest.main(verbosity=2)
