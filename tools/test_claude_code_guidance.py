"""Policy parity and bounded project routing for Claude's native execution loop."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import claude_code_guidance as policy


class ProfessionalGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)/'project'
        self.project.mkdir()
        (self.project/'.git').mkdir()

    def ordered_project_scan(self, names):
        """Preserve directory order without relying on filesystem enumeration order."""
        original = policy.os.scandir
        project = self.project

        class Entry:
            def __init__(self, name):
                self.name = name
                self.path = str(project/name)

            def is_file(self, *, follow_symlinks=True):
                return True

        class Scan:
            def __enter__(self):
                return iter(Entry(name) for name in names)

            def __exit__(self, *_args):
                return False

        def scan(path):
            return Scan() if Path(path) == project else original(path)

        return patch.object(policy.os, 'scandir', side_effect=scan)

    def test_long_term_rules_and_evidence_are_shared_without_foreign_runtime_commands(self):
        guide = policy.guidance()
        for heading in ['현재 상태·변경·검증','장기 개발·유지보수','MCP·컨텍스트','압축·재개','근거·도구','진행·최종 보고']:
            self.assertEqual(guide.count('## '+heading+'\n'), 1)
        for contract in ['같은 기능의 두 번째 구현','실제 공유 계약','현재 구간·diff','마이그레이션',
                         '검증은 완료 조건을 증명하는 최소 묶음','실제 버전·lockfile','미완성 파일의 저장/남은 범위']:
            self.assertIn(contract, guide)
        for foreign in ['`rea_analysis`','run_bounded_command.ps1','strata_restart_server','agents.build.steps','16000']:
            self.assertNotIn(foreign, guide)
        self.assertIn('실제 제공된 REA MCP 도구', guide)
        self.assertIn('대상 형식과 작업에 맞는 검색어', guide)
        self.assertIn('카탈로그 전체를 열거하지 말고', guide)
        self.assertIn('Windows Python은 프로젝트 가상환경 실행 파일을 우선 사용하고', guide)
        self.assertIn('WindowsApps 실행 별칭의 잘못된 경로로 실패하면', guide)
        self.assertIn('사용 가능한 `mcp__ccd_turn__wrap_up`을 호출한다', guide)
        self.assertIn('해당 앱 도구가 없는 CLI에서는 호출한 척하지 않는다', guide)

    def test_missing_shared_section_is_reported_instead_of_silent_policy_loss(self):
        with self.assertRaisesRegex(ValueError, '장기'):
            policy.shared_sections('## 현재\n내용\n', {'장기'})

    def test_duplicate_selected_sections_are_rejected_instead_of_combined(self):
        with self.assertRaisesRegex(ValueError, '중복.*장기'):
            policy.shared_sections('## 장기\n기준 A\n## 기타\n참고\n## 장기\n충돌하는 기준 B\n', {'장기'})

    def test_duplicate_recovery_policy_prevents_guidance_generation(self):
        root = Path(self.temp.name)/'templates'
        examples = root/'examples/claude'
        examples.mkdir(parents=True)
        for name in ('KOREAN_INSTRUCTIONS.md', 'STRATA_SESSION_RECOVERY_KO.md',
                     'game-engines/UNITY_AGENTS.md', 'game-engines/UNREAL_ENGINE_AGENTS.md',
                     'professional/DESKTOP_AGENTS.md'):
            body = (policy.ROOT/'examples/claude'/name).read_text(encoding='utf-8')
            if name == 'STRATA_SESSION_RECOVERY_KO.md':
                body += '\n## 현재 상태·변경·검증\n기존 기준을 덮는 중복 지침\n'
            target = examples/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '중복.*현재 상태'):
            policy.managed_guidance(self.project, root=root)

    def test_installed_policy_routes_to_embedded_rules_not_an_unshipped_template(self):
        for mode in (False, True):
            with self.subTest(lazy_cua_rea=mode):
                assets = policy.managed_guidance(self.project, lazy_cua_rea=mode)
                guide = assets['CLAUDE.md']
                self.assertFalse('`STRATA_SESSION_RECOVERY_KO.md`' in guide,
                                 'Installed policy refers to an unshipped source template')
                self.assertIn('실행·검증과 GUI 처리는 아래 Claude 실행·완료 및 CUA·권한 지침을 따른다.', guide)
                self.assertEqual(guide.count('## Claude 실행·완료\n'), 1)
                self.assertEqual(guide.count('## CUA·권한\n'), 1)
                self.assertNotIn('GUI 입력은 GUI 지침을 따른다.', guide)
                self.assertIn('GUI 입력은 아래 CUA·권한 지침을 따른다.', guide)

    def test_cua_guidance_matches_direct_and_lazy_mcp_delivery(self):
        direct = policy.guidance(lazy_cua_rea=False)
        lazy = policy.guidance(lazy_cua_rea=True)
        self.assertIn('직접 연결된 `cua-driver` MCP', direct)
        self.assertNotIn('agent-tools.search_tools', direct)
        self.assertIn('`agent-tools.search_tools`를 `server="cua-driver"`로 호출', lazy)
        self.assertIn('`agent-tools.call_tool`로 실행', lazy)
        self.assertNotIn('직접 연결된 `cua-driver` MCP', lazy)

    def test_desktop_guide_uses_the_existing_source_and_is_not_in_every_prompt(self):
        assets = policy.managed_guidance(self.project)
        source = (policy.ROOT/policy.DESKTOP_GUIDE).read_text(encoding='utf-8')
        self.assertTrue(assets['guidance/desktop.md'].endswith(source))
        self.assertNotIn('# 전문 데스크톱 프로젝트', assets['CLAUDE.md'])
        context = policy.hook_context({'hook_event_name':'UserPromptSubmit','cwd':str(self.project)})
        self.assertNotIn('# 전문 데스크톱 프로젝트', context)

    def test_desktop_routing_requires_ui_metadata_and_reuses_one_profile(self):
        for name, content in [
                ('wpf', '<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>'),
                ('forms', '<Project><PropertyGroup><UseWindowsForms>true</UseWindowsForms></PropertyGroup></Project>'),
                ('avalonia', '<Project><ItemGroup><PackageReference Include="Avalonia" /></ItemGroup></Project>')]:
            with self.subTest(name=name):
                path = self.project/'App.csproj'
                path.write_text(content, encoding='utf-8')
                self.assertEqual(policy.project_profile(self.project), 'desktop')
                self.assertIsNone(policy.project_engine(self.project))
                context = policy.hook_context({'hook_event_name':'SessionStart','cwd':str(self.project)})
                self.assertIn('# 전문 데스크톱 프로젝트', context)
                self.assertNotIn('# Unity 프로젝트 지침', context)
        (self.project/'App.csproj').write_text('<Project><PropertyGroup><OutputType>Exe</OutputType></PropertyGroup></Project>',encoding='utf-8')
        self.assertIsNone(policy.project_profile(self.project))

    def test_qt_core_and_commented_out_ui_do_not_become_desktop_projects(self):
        cmake = self.project/'CMakeLists.txt'
        for content in ['find_package(Qt6 REQUIRED COMPONENTS Core)', '# find_package(Qt6 COMPONENTS Widgets)']:
            cmake.write_text(content,encoding='utf-8')
            self.assertIsNone(policy.project_profile(self.project))
        cmake.write_text('find_package(Qt6 REQUIRED COMPONENTS Widgets)',encoding='utf-8')
        self.assertEqual(policy.project_profile(self.project), 'desktop')

    def test_engine_identity_takes_precedence_and_git_boundary_is_respected(self):
        (self.project/'App.csproj').write_text('<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>',encoding='utf-8')
        (self.project/'Game.uproject').write_text('{}',encoding='utf-8')
        self.assertEqual(policy.project_profile(self.project), 'unreal')
        child = self.project/'OtherRepository'
        child.mkdir()
        (child/'.git').mkdir()
        self.assertIsNone(policy.project_profile(child))

    def test_large_or_invalid_metadata_does_not_trigger_source_tree_scans(self):
        path = self.project/'App.csproj'
        for content in ['<'*70000, '<Project>invalid<', '<Project>'+' '*66000+'<UseWPF>true</UseWPF></Project>']:
            path.write_text(content,encoding='utf-8')
            self.assertIsNone(policy.project_profile(self.project))

    def test_unreal_marker_after_512_unrelated_entries_is_detected(self):
        (self.project/'Game.uproject').write_text('{}', encoding='utf-8')
        entries = [f'junk-{index}.txt' for index in range(512)] + ['Game.uproject']
        with self.ordered_project_scan(entries):
            self.assertEqual(policy.project_profile(self.project), 'unreal')

    def test_late_unreal_marker_takes_precedence_over_early_desktop_project(self):
        (self.project/'App.csproj').write_text(
            '<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>', encoding='utf-8')
        (self.project/'Game.uproject').write_text('{}', encoding='utf-8')
        entries = ['App.csproj'] + [f'junk-{index}.txt' for index in range(600)] + ['Game.uproject']
        with self.ordered_project_scan(entries):
            self.assertEqual(policy.project_profile(self.project), 'unreal')

    def test_desktop_project_after_32_non_ui_projects_is_detected(self):
        names = [f'Core{index}.csproj' for index in range(40)]
        for name in names:
            (self.project/name).write_text('<Project />', encoding='utf-8')
        (self.project/'Ui.csproj').write_text(
            '<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>', encoding='utf-8')
        with self.ordered_project_scan(names + ['Ui.csproj']):
            self.assertEqual(policy.project_profile(self.project), 'desktop')

    def test_truncated_directory_scan_does_not_confirm_early_desktop_project(self):
        (self.project/'App.csproj').write_text(
            '<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>', encoding='utf-8')
        limit = getattr(policy, 'MAX_PROJECT_DIRECTORY_ENTRIES', 16384)
        entries = ['App.csproj'] + [f'junk-{index}.txt' for index in range(limit)] + ['Game.uproject']
        with self.ordered_project_scan(entries):
            self.assertIsNone(policy.project_profile(self.project))

    def test_compact_resume_context_preserves_scope_without_creating_project_files(self):
        before = list(self.project.iterdir())
        context = policy.hook_context({'hook_event_name':'SessionStart','source':'compact','cwd':str(self.project)})
        self.assertIn('압축은 작업 완료나 새 실행 허가가 아니다', context)
        self.assertIn('미완료 범위만 이어간다', context)
        self.assertEqual(list(self.project.iterdir()), before)
        normal = policy.hook_context({'hook_event_name':'SessionStart','source':'startup','cwd':str(self.project)})
        self.assertNotIn(policy.COMPACT_RESUME, normal)


if __name__ == '__main__':
    unittest.main()
