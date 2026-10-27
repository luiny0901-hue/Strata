"""Project shared development policy into Claude Code without an extra agent loop."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path.home()/'.config/strata/claude-code'
MANAGED = '<!-- strata-claude-code:v1 -->'
ENGINE_RULES = {'unity': 'UNITY_AGENTS.md', 'unreal': 'UNREAL_ENGINE_AGENTS.md'}
DESKTOP_GUIDE = Path('examples/claude/professional/DESKTOP_AGENTS.md')

NATIVE_EXECUTION = """## Claude 실행·완료

- Claude Code의 실제 도구·내장 압축·세션 재개를 사용한다. 경로가 주어진 작은 파일은 직접 Read한다. 큰 파일·긴 로그의 국소 작업은 offset/limit으로 필요한 함수·타입과 앞뒤 문맥부터 읽고, 위치가 없으면 해당 파일·모듈에 한정한 Grep으로 줄 위치를 찾는다. 호출부·계약·검증에 부족한 범위는 확장하되 한도 오류 회피용 allow_large를 상시 켜지 않는다. 남은 컨텍스트 한도 오류는 같은 인자로 반복하지 않고 오류의 허용량과 이미 반환된 범위를 기준으로 미확인 구간만 줄여 읽는다. 충분히 확보한 파일 목록·내용은 같은 목적의 Glob·셸 조회로 반복하지 않는다. 셸은 비대화형·유한 timeout·종료 코드·필요한 로그로 확인한다. 독립 조회는 지원되는 병렬 도구로 묶고 의존 변경은 순서대로 한다. 긴 빌드에는 예상 시간과 여유를 주고 조용하다는 이유만으로 중복 실행·임의 중단하지 않는다. 고정 sleep보다 기한이 있는 준비 조건을 확인한다.
- 파일 저장·수정·명령 성공은 해당 실제 도구 호출의 성공 결과가 있을 때만 보고한다. 도구 호출 전에는 예정·진행 상태로만 설명한다. 코드·명령을 답변에 적거나 호출을 계획한 것은 실행이 아니다. 실행 근거가 없거나 도구가 실패했으면 미실행·미완료로 보고한다. 필수 도구·빌드·하위 작업은 현재 요청 안에서 실제 결과를 확인한다. 백그라운드로 전환됐다면 소유 작업 ID·로그·완료 상태를 사용하고 같은 일을 새로 실행하지 않는다. 필수 검증을 남긴 채 완료로 보고하거나 나중의 자동 보고를 약속하지 않는다. 사용자가 요청한 상시 서버·watcher만 계속 실행하고 소유 프로세스·health·남은 상태를 보고한다.
- Claude Desktop Code에서 계획을 유지했거나 파일을 바꾸거나 도구·명령을 실행한 턴은 최종 답변 전에 사용 가능한 `mcp__ccd_turn__wrap_up`을 호출한다. 2~3문장 recap에 현재 상태와 미완료·미검증 항목을 담는다. 완료 도구의 추가 선택이 불필요하면 recap만 전달하고, 선택이 필요할 때만 실제 도구 스키마의 선택지를 사용한다. 해당 앱 도구가 없는 CLI에서는 호출한 척하지 않는다.
- 코드는 기존 모듈 경계와 실제 변경 범위에 맞춰 저장한다. 국소 수정에 전체 파일을 재생성하거나 짧은 내용을 작은 Write·셸 append 호출로 잘게 나누지 않는다. 출력 한도에 가까운 큰 구현은 일관된 변경 묶음으로 나누며 한도에 가까운 거대한 도구 호출·셸 문자열로 몰아 쓰지 않는다. 잘림·timeout·불확실한 실행 뒤에는 실제 파일·diff·소유 작업을 확인하고 저장된 부분을 보존한 채 남은 범위만 처리한다.
- 수락 조건을 충족하면 소유 CUA 세션 등 임시 자원을 정리하고 최종 보고 후 종료한다. 중지·취소·완료 뒤 늦은 알림이나 압축이 새 작업 허가가 되지 않는다. 저장·설치·MCP 부작용이 취소만으로 롤백됐다고 가정하지 않는다. 자기 추론 서버의 재시작은 제공된 관리 도구와 체크포인트가 있을 때만 수행하고, 없으면 셸에서 자기 서버를 종료하지 않는다.

## CUA·권한

{cua_access} 정확한 창을 식별하고 최신 화면·요소 토큰으로 조작하며 background를 우선한다. 사용자 입력에 영향을 주는 전경 입력은 approved_foreground_action의 실제 사람 승인 뒤에만 사용한다. 승인창·UAC·보안 데스크톱을 자동 조작하거나 다른 셸/전역 입력으로 우회하지 않는다. 현재 세션의 승인 상태를 다른 세션이나 작업에 공유하지 않는다. 현재 계정에서 권한이 부족하거나 실제 사용자 확인을 기다리는 단계는 이유·필요한 행동·소유 상태를 기록하고 종속 작업만 보류한다. 이미 완료된 작업을 늦은 승인으로 중복 실행하거나 무기한 기다리지 않는다."""

COMPACT_RESUME = ('압축은 작업 완료나 새 실행 허가가 아니다. 최신 요청·금지·기존 체크포인트와 실제 파일·diff·'
                  '소유 작업 상태를 대조하고 미완료 범위만 이어간다. 유효한 구현·검증을 처음부터 반복하거나 '
                  '별도 병렬 상태 문서를 만들지 않는다.')


def shared_sections(text, titles):
    sections = re.split(r'(?m)^## ', text)
    available = {section.partition('\n')[0] for section in sections[1:]}
    missing = titles-available
    if missing:
        raise ValueError('지침 정본의 필수 절이 없습니다: '+', '.join(sorted(missing)))
    return '\n\n'.join('## '+section.strip() for section in sections[1:]
                       if section.partition('\n')[0] in titles)


def guidance(root=ROOT, profile=PROFILE, *, lazy_cua_rea=False):
    basic = (root/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
    recovery = (root/'examples/claude/STRATA_SESSION_RECOVERY_KO.md').read_text(encoding='utf-8')
    if '<!-- strata-authoring-policy:v1 -->' not in recovery:
        raise ValueError('코드 작성 지침의 정본 표식이 없습니다.')
    common = shared_sections(basic, {
        '언어', '요청 해석과 범위', '산출물 형태', '역할과 기술 선택', '품질',
        '게임 플랫폼', '창작·게임 스토리', '근거·도구', '진행·최종 보고',
    })
    replacements = {
        '실행·중복 방지·검증은 `STRATA_SESSION_RECOVERY_KO.md`, GUI는 CUA 지침을 따른다.':
            '실행·검증과 GUI 처리는 아래 Claude 실행·완료 및 CUA·권한 지침을 따른다.',
        '`rea_analysis`에 읽기 전용 증거 수집을 맡긴다.':
            '실제 제공된 REA MCP 도구로 읽기 전용 증거를 수집한다.',
        '에이전트가 별도 대상 프로젝트에 구현한다.':
            'Claude Code가 별도 대상 프로젝트에 구현한다.',
        '실행 종료 기준은 복구 지침을 따르며':
            '실행 종료 기준은 아래 Claude 실행 지침을 따르며',
        '입력·오류 처리는 GUI 지침을 따른다.':
            '입력·오류 처리는 아래 CUA 지침을 따른다.',
    }
    for original, replacement in replacements.items():
        common = common.replace(original, replacement)
    current = shared_sections(recovery, {'현재 상태·변경·검증'})
    # Keep the Claude guidance independent from client plug-in output limits.
    current = current.replace('16000자는 한 write 호출의 크기이며 최종 파일 크기나 모듈 분할 기준이 아니다. ', '')
    paths = '\n'.join(f'- {kind}: `{(profile/"guidance"/(kind+".md")).as_posix()}`'
                      for kind in [*ENGINE_RULES, 'desktop'])
    cua_access = (
        'GUI가 필요한 경우에만 `agent-tools.search_tools`를 `server="cua-driver"`로 호출한다. '
        '반환된 정확한 도구 이름과 스키마만 `agent-tools.call_tool`로 실행한다. '
        '자식 CUA 서버를 직접 호출하거나 검색 결과에 없는 도구를 추측하지 않는다.'
        if lazy_cua_rea else
        'GUI가 필요한 경우에만 직접 연결된 `cua-driver` MCP를 사용한다.'
    )
    execution = NATIVE_EXECUTION.format(cua_access=cua_access)
    return '\n\n'.join([
        MANAGED, '# Strata용 Claude Code 지침',
        '현재 도구와 실행 루프는 Claude Code가 소유한다. 실제 제공된 Read·Edit·Write·Bash/PowerShell·MCP 도구를 사용한다. 현재 환경에 없는 도구를 호출하지 않는다.',
        common,
        '## 전문 프로젝트 지침\n\n프로젝트의 CLAUDE.md·AGENTS.md·기존 빌드 절차를 확인한다. '
        '시작·재개·압축 후에는 실제 프로젝트 표식으로 확인된 Unity·Unreal·전문 데스크톱 지침 하나가 추가된다. '
        '표식 없는 새 프로젝트나 다른 하위 프로젝트를 다룰 때는 구현 전에 해당 지침만 읽는다. '
        '일반 작업에 모든 상세 지침을 읽거나 CLI·웹·모바일·서버에 데스크톱 구조를 강제하지 않는다. '
        '지침은 실제 엔진·SDK·에셋·디자이너 검수·실기 검증을 대신하지 않는다.\n\n'+paths,
        current,
        shared_sections(recovery, {'장기 개발·유지보수', 'MCP·컨텍스트', '압축·재개'}),
        execution,
    ])+'\n'


def managed_guidance(profile, root=ROOT, *, lazy_cua_rea=False):
    assets = {'CLAUDE.md': guidance(root, profile, lazy_cua_rea=lazy_cua_rea)}
    for engine, template in ENGINE_RULES.items():
        body = (root/'examples/claude/game-engines'/template).read_text(encoding='utf-8')
        assets[f'guidance/{engine}.md'] = MANAGED+'\n\n'+body
    assets['guidance/desktop.md'] = MANAGED+'\n\n'+(root/DESKTOP_GUIDE).read_text(encoding='utf-8')
    return assets


def language_reminder(root=ROOT):
    return ('진행·완료 설명은 기본 한국어다. 뜻이 분명한 통용 한국어에 영문 동사·괄호 영문 풀이를 '
            '덧붙이지 않는다. 영문 질문·로그만으로 영어로 바꾸지 않는다. 사용자가 명시한 다른 응답/산출물 언어, '
            '코드·식별자·원문·필수 요약 제목은 보존한다. 이 알림은 작업 범위나 실행 허가를 추가하지 않는다.')


def validate_managed_guidance(profile, assets, previous):
    """Refuse to replace Claude guidance that the user edited after setup."""
    digests = dict(previous.get('managed_guidance_sha256', {}))
    if previous.get('guidance_sha256'):
        digests.setdefault('CLAUDE.md', previous['guidance_sha256'])
    for name, content in assets.items():
        path = profile/name
        if not path.exists():
            continue
        current = path.read_bytes()
        expected = digests.get(name)
        if ((expected and hashlib.sha256(current).hexdigest() != expected)
                or (not expected and current != content.encode('utf-8'))):
            raise ValueError(f'수동 변경된 지침을 먼저 확인하세요. 기존 내용은 보존합니다: {path}')


def _metadata(path, limit=65536):
    try:
        with path.open('rb') as stream:
            data = stream.read(limit+1)
        return data.decode('utf-8-sig') if len(data) <= limit else None
    except (OSError, UnicodeError):
        return None


def _desktop_project(candidate, project_files):
    for name in project_files[:32]:
        content = _metadata(candidate/name)
        if content is None:
            continue
        try:
            document = ET.fromstring(content)
        except ET.ParseError:
            continue
        for node in document.iter():
            tag = node.tag.rsplit('}', 1)[-1]
            if tag in ('UseWPF', 'UseWindowsForms', 'UseWinUI') and (node.text or '').strip().lower() == 'true':
                return True
            if tag == 'PackageReference' and node.get('Include') in ('Avalonia', 'Microsoft.WindowsAppSDK'):
                return True
    cmake = _metadata(candidate/'CMakeLists.txt')
    if cmake:
        cmake = '\n'.join(line.split('#', 1)[0] for line in cmake.splitlines())
        if re.search(r'find_package\s*\(\s*Qt[56]\b[^)]*\b(?:Widgets|Quick|Gui)\b', cmake):
            return True
    return False


def project_profile(project):
    """Read bounded nearby metadata; never walk source/asset/build trees."""
    project = Path(project).expanduser().resolve()
    for candidate in [project, *list(project.parents)[:7]]:
        unity = (candidate/'ProjectSettings/ProjectVersion.txt').is_file()
        unreal = False
        project_files = []
        try:
            with os.scandir(candidate) as entries:
                for index, entry in enumerate(entries):
                    if index >= 512:
                        break
                    if entry.name.endswith('.uproject') and entry.is_file(follow_symlinks=False):
                        unreal = True
                    elif entry.name.endswith('.csproj') and entry.is_file(follow_symlinks=False):
                        project_files.append(entry.name)
        except OSError:
            return None
        if unity or unreal:
            return 'unity' if unity and not unreal else 'unreal' if unreal and not unity else None
        if _desktop_project(candidate, project_files):
            return 'desktop'
        if (candidate/'.git').exists() or candidate == Path.home():
            break
    return None


def project_engine(project):
    kind = project_profile(project)
    return kind if kind in ENGINE_RULES else None


def hook_context(event, root=ROOT):
    context = language_reminder(root)
    if event.get('hook_event_name') == 'SessionStart':
        session_id = event.get('session_id')
        if isinstance(session_id, str) and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', session_id):
            context += '\n현재 native Claude Code session_id: ' + session_id + ' (Desktop local_ ID와 다름).'
        kind = project_profile(event.get('cwd') or Path.cwd())
        if kind:
            template = root/DESKTOP_GUIDE if kind == 'desktop' else root/'examples/claude/game-engines'/ENGINE_RULES[kind]
            body = template.read_text(encoding='utf-8')
            marker = 'project' if kind == 'desktop' else 'engine'
            context += f'\n\n현재 프로젝트 종류: {kind} [strata-{marker}-context:{kind}:v1]\n\n'+body
        if event.get('source') == 'compact':
            context += '\n\n'+COMPACT_RESUME
    return context
