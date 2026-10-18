"""CPU-only tests for project-scoped Unreal and Unity AGENTS.md templates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.install_engine_project_guidance import TEMPLATES, install_guidance  # noqa: E402


class EngineGuidanceTests(unittest.TestCase):
    def test_each_template_is_copied_to_a_new_project_root(self):
        for engine, template in TEMPLATES.items():
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary) / "game"
                project.mkdir()

                destination = install_guidance(project, engine)

                self.assertEqual(destination, project / "AGENTS.md")
                self.assertEqual(destination.read_bytes(), template.read_bytes())

    def test_existing_project_guidance_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "game"
            project.mkdir()
            existing = project / "AGENTS.md"
            existing.write_text("user project instructions\n", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                install_guidance(project, "unity")

            self.assertEqual(existing.read_text(encoding="utf-8"), "user project instructions\n")

    def test_invalid_engine_or_project_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            with self.assertRaisesRegex(ValueError, "Project directory"):
                install_guidance(missing, "unreal")
            project = Path(temporary) / "game"
            project.mkdir()
            with self.assertRaisesRegex(ValueError, "Unsupported engine"):
                install_guidance(project, "godot")


if __name__ == "__main__":
    unittest.main(verbosity=2)
