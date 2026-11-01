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

    def test_execution_evidence_is_shared_with_codex_without_desktop_only_tools(self):
        from tools.strata_client_settings import _codex_guide
        for guide in (policy.guidance(), _codex_guide()):
            self.assertEqual(guide.count(policy.CLIENT_EXECUTION), 1)
            self.assertIn('0개 실행·과거 로그·다른 빌드의 통과', guide)
            self.assertIn('재시도 전에 실제 파일·diff·소유 실행 상태', guide)
            self.assertEqual(guide.count(policy.SHARED_PLANNING), 1)
            self.assertIn('처음에는 딱 하나만 진행 중이고 나머지는 대기', guide)
            self.assertIn('처음부터 모든 항목을 완료로 표시하지 않고', guide)
            self.assertIn('최종 보고에서 목록 상태를 실제 결과와 일치시킨다', guide)
        self.assertNotIn('mcp__ccd_turn__wrap_up', _codex_guide())
        self.assertNotIn('mcp__ccd_turn__update_plan', _codex_guide())

    def test_progress_stays_korean_after_handling_english_material(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        self.assertIn('영어 문서·로그·검색 결과를 읽거나 처리한 직후에도', reminder)
        self.assertIn('새 진행·백그라운드 대기 안내까지 모든 사용자 표시 문장은 한국어로 시작하고', reminder)
        self.assertIn('다음 문장부터 바로 한국어로 돌아온다', reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('진행 문장이 영어로 빠지면 중단하지 말고', guide)

    def test_korean_policy_covers_tool_labels_and_choices_without_changing_code(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        for term in ['description', '진행 제목', '체크리스트', '질문 선택지',
                     '후속 버튼 label/message', '명령·경로·JSON 키·코드·원문은 변경하지 않는다',
                     '깨진 도구 결과는 추측해 인용하지 않는다',
                     '대화 보고는 자연스러운 존댓말', '준비·예정·미실행·실패·검증 통과를 구분',
                     '표현 예시는 성공 근거가 아니다', '결정할 일이 없으면 선택지를 만들지 않는다']:
            self.assertIn(term, reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('질문의 제목·선택지 설명', guide)
        self.assertIn('인코딩을 명시한 읽기', guide)
        self.assertIn('언어 교정만을 위한 모델 재호출이나 도구 실행 재시도는 하지 않는다', guide)

    def test_conversation_and_fiction_keep_distinct_registers(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        for phrase in ['일상 대화에는 업무 보고체를 붙이지 않고',
                       '성과·경험·감정을 단정하지 않는다',
                       '보고용 존댓말을 강제하지 않는다',
                       '설정·사건·분량·의도된 문체는 보존한다']:
            self.assertIn(phrase, reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('같은 뜻의 강조·동작·감정 설명을 불필요하게 반복하지 않는다', guide)
        self.assertIn('자연스러움을 이유로 줄거리나 인물 성격을 바꾸지 않는다', guide)
        self.assertIn('대명사는 장면 전체에서 하나로 일치시킨다', guide)
        self.assertIn('대명사는 앞선 호칭·성별과 일치시킨다', reminder)

    def test_fiction_length_and_scene_conditions_are_countable(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        self.assertIn('요청 분량은 문단·대사 수로 세어 맞추고', reminder)
        self.assertIn('명시된 결말·소품 조건은 최종 문단에서 확인한다', reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('문단·대사 수 같은 셀 수 있는 단위로 완성 원고를 세어 맞추고', guide)
        self.assertIn('결말·소품처럼 명시된 장면 조건은 최종 문단에서 직접 확인한다', guide)

    def test_scene_person_length_plan_and_multi_request_replies(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        self.assertIn('아직 일어나지 않은 미래 결과를 ‘분명’하다고도 말하지 않는다', reminder)
        self.assertIn('여러 요청이 함께 주어지면 하나도 빼지 않고 지정한 문장 수에 맞춘다', reminder)
        self.assertIn('요청한 시점·시제·서술 인칭·인물 말투를 유지하며', reminder)
        self.assertIn('하한을 채울 문단 수를 먼저 정하고 요청 분량은 문단·대사 수로 세어 맞추고', reminder)
        self.assertIn('짧은 장면 하나로 줄이지 않으며', reminder)
        self.assertIn('말투 지시는 서술에 ‘존댓말’·‘반말’이라는 이름으로 옮기지 않고 실제 대화로 보여준다', reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('아직 일어나지 않은 미래의 결과·감정을 ‘분명’하다고 확정하지도 않는다', guide)
        self.assertIn('여러 요청이 함께 주어지면 하나도 빼지 않고 지정한 문장 수 안에 모두 담는다', guide)
        self.assertIn('서술 인칭이 첫 문장부터 끝까지 어긋나지 않으며', guide)
        self.assertIn('하한을 채울 문단 수를 먼저 정해 둔다', guide)
        self.assertIn('글자 수 범위로 요청받은 단편은 본문 문단을 서너 개 이상으로 펼쳐 쓴다', guide)
        self.assertIn("말투 지시는 서술에 ‘존댓말’·‘반말’이라는 이름으로 옮기지 않고 실제 대화로 보여준다", guide)

    def test_ui_strings_follow_screen_word_conventions(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        self.assertIn('같은 화면 단추·메뉴 이름을 ‘확인’·‘저장’ 같은 명사형으로 통일하고', reminder)
        self.assertIn('오류 문구에 원인과 다음 행동을 담고', reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('같은 화면의 단추·메뉴 이름은 한 가지 형태로 통일하고', guide)
        self.assertIn('같은 기능의 말은 화면 전체에서 하나로 쓴다', guide)
        self.assertIn('영문 말이나 이중 피동을 그대로 옮기지 않고 원인과 다음 행동', guide)
        self.assertIn('“네, 제안합니다” 같은 도입·제안 문장을 붙이지 않는다', guide)

    def test_extended_conversation_preserves_terms_and_user_canon(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        for phrase in ['최신 정정값·주체·단위와 사례를 구분', '비유로 기술적 의미·한계를 바꾸거나',
                       '앞선 생성 오류보다 사용자 지정 관계·호칭·말투·시점·종료 조건을 우선',
                       '직전 장면 끝의 소유물·위치·지식과 다음 시작을 대조']:
            self.assertIn(phrase, reminder)
        self.assertIn(reminder, _codex_guide())
        self.assertIn('이미 설명한 전문용어를 매번 다시 풀지 않는다', policy.guidance())

    def test_translation_preserves_roles_and_distinguishes_interpretation(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        for phrase in ['번역은 행위자·대상·수식 관계·호칭·부정·조건·수치·단위를 보존',
                       '의도나 금지 방향을 뒤집지 않는다', '해설의 사실과 가능한 해석을 나눠',
                       '번역문만 요청하면 해설을 붙이지 않는다']:
            self.assertIn(phrase, reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('백분율과 퍼센트포인트', guide)
        self.assertIn('대명사의 지시 대상이 모호하면 모호함을 보존', guide)

    def test_foreign_names_keep_requested_spelling_and_scene_roles(self):
        from tools.strata_client_settings import _codex_guide
        reminder = policy.language_reminder()
        self.assertIn('외국 회사·제품명은 통용 표기나 지정된 원어를 유지', reminder)
        self.assertIn('입력에 적힌 원어 표기나 `친구 A` 같은 축약은 유지 지시가 아니라면 답에 옮기지 않고', reminder)
        self.assertIn('그 표기를 본문 전체에서 일관되게 쓴다', reminder)
        self.assertIn('무관한 인과를 붙이지 않는다', reminder)
        self.assertIn('작성 지시를 소설 본문에 그대로 복사하지 않고', reminder)
        self.assertIn(reminder, _codex_guide())
        guide = policy.guidance()
        self.assertIn('조사는 실제 읽는 소리에 맞추고', guide)
        self.assertIn('원어 표기를 유지하라는 요청은 한글 음역으로 바꾸지 않는다', guide)

    def test_performance_decisions_reach_both_clients_from_shared_source(self):
        from tools.strata_client_settings import _codex_guide
        scope = policy.scope_policy()
        for contract in [
                '쉽고 빠르게 구현된다는 이유만으로 이 기준을 못 맞추는 방법을 고르지 않는다',
                '대표·최대 데이터 크기, 동시 부하',
                '미정 값은 가정과 미확인으로 구분',
                '설계만 요청받았으면 선택 근거와 검증 방법까지만',
                '같은 입력·기기·빌드 구성·정밀도·동시 부하',
                '정확성 및 필요한 성능 지표를 함께 비교',
                '전송·복사·동기화·메모리 비용까지 포함',
                '정확도·보안·호환성·필수 기능을 몰래 낮춰',
                '성능과 무관한 작은 수정에 별도 벤치마크를 강제하지 않는다']:
            self.assertIn(contract, scope)
        for guide in (policy.guidance(), _codex_guide()):
            self.assertEqual(guide.count(scope), 1)

    def test_progress_reports_reach_both_clients_without_requiring_thinking_display(self):
        from tools.strata_client_settings import _codex_guide
        for guide in (policy.guidance(), _codex_guide()):
            self.assertEqual(guide.count('## 진행·최종 보고\n'), 1)
            for contract in ['첫 도구 호출 전에', '일반 답변 본문으로 설명한다',
                             '모든 설명을 최종 답변까지 미루지 않는다',
                             '성공·완료는 결과 확인 뒤에만', '미확인 진척률']:
                self.assertIn(contract, guide)
        self.assertIn(policy.progress_policy(), _codex_guide())
        self.assertNotIn('실행 종료 기준은 복구 지침을 따르며', _codex_guide())

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
