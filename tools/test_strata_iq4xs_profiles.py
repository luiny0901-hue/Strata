"""CPU-only tests for the portable UD-IQ4_XS setup helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strata_iq4xs_profiles import (
    MODEL_KEY,
    MODEL_REVISION,
    SHARD_NAMES,
    render_profile,
    validate_templates,
    verify_assets,
)


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
                self.assertEqual(profile["effort_position"], "end")
                self.assertEqual(
                    profile["args"][profile["args"].index("--pack") + 1],
                    str(data_root / "packs" / "unsloth-ud-iq4_xs"),
                )
                self.assertEqual(profile["args"][profile["args"].index("--max-context") + 1], "262144")
                self.assertEqual(profile["args"][profile["args"].index("--vram-reserve-mib") + 1], "448")
                self.assertEqual(profile["args"][profile["args"].index("--prefill") + 1],
                                 "auto:16384" if mode == "on" else "auto")
                for option, value in (("--conversation-cache-mib", "8192"),
                                      ("--conversation-cache-slots", "2"),
                                      ("--conversation-cache-min-free-mib", "8192"),
                                      ("--conversation-cache-min-tokens", "16384")):
                    if mode == "on":
                        self.assertEqual(profile["args"].count(option), 1)
                        self.assertEqual(profile["args"][profile["args"].index(option) + 1], value)
                    else:
                        self.assertNotIn(option, profile["args"])
                self.assertIn("--ple-gguf", profile["args"])
                self.assertTrue(profile["args"][profile["args"].index("--native") + 1].endswith("-00001-of-00003.gguf"))
                self.assertTrue(profile["args"][profile["args"].index("--ple-gguf") + 1].endswith("-00002-of-00003.gguf"))
                self.assertEqual(profile["vision"]["gpu"], False)
                self.assertIn(str(strata_root), profile["exe"])
                self.assertIn(str(data_root), profile["args"][1])
                self.assertNotIn("@", output.read_text(encoding="utf-8"))

    def test_cache_limits_and_duplicates_are_checked_before_adoption(self) -> None:
        for invalid in ("budget", "duplicate", "threshold"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "profiles").mkdir()
                for mode in ("on", "off"):
                    name = f"strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-{mode}.json.template"
                    profile = json.loads((ROOT / "profiles" / name).read_text(encoding="utf-8"))
                    if mode == "on":
                        if invalid == "budget":
                            profile["args"][profile["args"].index("--conversation-cache-mib") + 1] = "0"
                        elif invalid == "threshold":
                            profile["args"][profile["args"].index("--conversation-cache-min-tokens") + 1] = "32768"
                        else:
                            profile["args"].extend(["--conversation-cache-mib", "8192"])
                    (root / "profiles" / name).write_text(json.dumps(profile), encoding="utf-8")
                with self.assertRaises(AssertionError):
                    validate_templates(root)


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
