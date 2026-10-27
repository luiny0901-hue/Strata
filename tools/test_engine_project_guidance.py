"""CPU-only tests for project-scoped Unreal and Unity AGENTS.md templates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.install_engine_project_guidance import TEMPLATES, install_guidance  # noqa: E402


class EngineGuidanceTests(unittest.TestCase):
    def test_quality_criteria_cover_play_visuals_ui_and_measured_performance(self):
        for engine,template in ((k,v) for k,v in TEMPLATES.items() if k!="desktop"):
            with self.subTest(engine=engine):
                text=template.read_text(encoding='utf-8')
                for term in ('아트 방향','대상 기기','프레임','메모리','카메라','애니메이션','VFX','HUD','포커스','로딩','복구','라이선스'):
                    self.assertIn(term,text)
                self.assertEqual(text.count('## 검증과 보고'),1)

    def test_global_ui_and_game_rules_are_available_to_remote_client_setup(self):
        text=(ROOT/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
        self.assertIn('최신 공식 플랫폼 지침',text)
        self.assertIn('반응형',text)
        self.assertIn('접근성',text)
        self.assertIn('대표 플레이 구간',text)
        self.assertIn('미완성 범위를 명시',text)

    def test_each_template_is_copied_to_a_new_project_root(self):
        for engine, template in TEMPLATES.items():
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary) / "game"
                project.mkdir()

                destination = install_guidance(project, engine)

                self.assertEqual(destination, project / "AGENTS.md")
                self.assertEqual(destination.read_bytes(), template.read_bytes())

    def test_desktop_profile_and_cli_alias(self):
        import subprocess,json
        text=TEMPLATES['desktop'].read_text(encoding='utf-8')
        self.assertIn('HTML/Canvas/Three.js/브라우저 데모로 대체하지 않는다',text)
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(ROOT/'tools/install_engine_project_guidance.py'),'--profile','desktop','--project',directory],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0)
            self.assertEqual((Path(directory)/'AGENTS.md').read_bytes(),TEMPLATES['desktop'].read_bytes())

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

    def test_nonoverwrite_does_not_depend_on_a_racy_exists_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)
            existing=project/'AGENTS.md'
            existing.write_text('concurrent user instructions',encoding='utf-8')
            with patch.object(Path,'exists',return_value=False):
                with self.assertRaisesRegex(FileExistsError,'Refusing to overwrite'):
                    install_guidance(project,'unity')
            self.assertEqual(existing.read_text(encoding='utf-8'),'concurrent user instructions')


if __name__ == "__main__":
    unittest.main(verbosity=2)
