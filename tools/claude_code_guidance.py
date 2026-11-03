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
MAX_PROJECT_DIRECTORY_ENTRIES = 16384
MAX_PROJECT_METADATA_FILES = 128

CUA_INPUT_POLICY = 'GUI의 마우스·키보드 입력은 CUA로 수행한다. 정확한 창을 식별하고 최신 화면·요소 토큰을 사용하며, 사용자 입력을 방해하지 않는 background를 먼저 사용한다. 전송 성공만으로 동작 완료를 판단하지 않고 대상 상태 변화를 확인한다. background 미지원 또는 미실행이 확인된 동작만 approved_foreground_action으로 실제 사람 승인을 받아 CUA 전경 입력을 사용한다. 결과가 불명확하면 상태부터 확인하고 같은 입력을 재전송하지 않는다. 승인 후에도 가능한 동작은 background를 유지한다. 승인 범위·수명은 현재 연결이 실제 제공하는 범위만 사용하고, 승인 거부·만료·승인 기능 부재이면 해당 GUI 단계와 의존 작업만 보류한다. 사용자 입력을 사용하는 2차 경로도 CUA를 통해서만 수행하며 다른 셸·전역 입력으로 우회하지 않는다. UAC·신뢰·권한 확인창·보안 데스크톱과 승인창은 자동 조작하지 않는다.'

CLIENT_EXECUTION = """- 유한 명령은 소유 실행 ID의 종료·종료 코드·필요한 산출물이 확인되면 즉시 다음 단계로 간다. 계속 켜둘 GUI·서버는 대상 창·health·준비 로그 등 필요한 준비 조건을 확인하고 앱 종료까지 기다리지 않는다. 셸 창 종료나 프롬프트 표시만으로 자식 빌드의 완료를 판단하지 않는다.
- 파일 저장·수정·명령 성공은 해당 실제 도구 호출의 성공 결과가 있을 때만 보고한다. 도구 호출 전에는 예정·진행 상태로만 설명한다. 코드·명령을 답변에 적거나 호출을 계획한 것은 실행이 아니다. 실행 근거가 없거나 도구가 실패했으면 미실행·미완료로 보고한다. 필수 도구·빌드·하위 작업은 현재 요청 안에서 실제 결과를 확인한다. 백그라운드로 전환됐다면 소유 작업 ID·로그·완료 상태를 사용하고 같은 일을 새로 실행하지 않는다. 필수 검증을 남긴 채 완료로 보고하거나 나중의 자동 보고를 약속하지 않는다. 사용자가 요청한 상시 서버·watcher만 계속 실행하고 소유 프로세스·health·남은 상태를 보고한다.
- MCP의 isError·명령 종료 코드·실제 산출물을 확인한다. 전송 성공은 동작 성공이 아니다. timeout·연결 끊김은 미실행 증거가 아니므로 재시도 전에 실제 파일·diff·소유 실행 상태를 확인한다. 인증·권한·사용량 한도 오류를 같은 호출의 반복이나 보호 설정 해제로 우회하지 않는다. 막힌 작업과 의존 작업만 보류하고 허가된 독립 작업은 계속한다.
- 검증은 실행 수·건너뜀·종료 코드와 요청한 동작의 결과로 판단한다. 0개 실행·과거 로그·다른 빌드의 통과·모델의 완료 문구를 현재 작업의 성공 증거로 삼지 않는다. 실패한 검사를 삭제하거나 요구와 무관하게 기대값을 바꿔 통과시키지 않는다.
- 수락 조건을 충족하면 소유 CUA 세션 등 임시 자원을 정리하고 최종 보고 후 종료한다. 중지·취소·완료 뒤 늦은 알림이나 압축이 새 작업 허가가 되지 않는다. 저장·설치·MCP 부작용이 취소만으로 롤백됐다고 가정하지 않는다. 자기 추론 서버의 재시작은 제공된 관리 도구와 체크포인트가 있을 때만 수행하고, 없으면 셸에서 자기 서버를 종료하지 않는다."""

SHARED_PLANNING = ('클라이언트가 작업 목록·계획 도구를 제공하면 파일을 바꾸거나 여러 단계로 진행되는 작업에서 '
                   '처음에 전체 목록을 만들되 처음에는 딱 하나만 진행 중이고 나머지는 대기이며, 단계가 끝날 때마다 '
                   '그 결과를 근거로 갱신하고, 최종 보고에서 목록 상태를 실제 결과와 일치시킨다. 처음부터 모든 항목을 '
                   '완료로 표시하지 않고, 목록을 만든 것만으로 진행했다고 하지 않으며, 실행 증거 없이 항목을 끝난 것으로 '
                   '표시하지 않고, 요청에 없는 항목으로 목록을 늘리지 않는다. 그 도구가 없는 환경에서는 호출한 척하지 '
                   '않고, 대신 단계가 3개 이상 이어지는 작업에서 짧은 번호 진행 목록을 유지하고 최종 보고에서 완료·미검증을 구분한다.')

NATIVE_EXECUTION = """## Claude 실행·완료

- Claude Code의 실제 도구·내장 압축·세션 재개를 사용한다. 경로가 주어진 작은 파일은 직접 Read한다. 큰 파일·긴 로그의 국소 작업은 offset/limit으로 필요한 함수·타입과 앞뒤 문맥부터 읽고, 위치가 없으면 해당 파일·모듈에 한정한 Grep으로 줄 위치를 찾는다. 호출부·계약·검증에 부족한 범위는 확장하되 한도 오류 회피용 allow_large를 상시 켜지 않는다. 남은 컨텍스트 한도 오류는 같은 인자로 반복하지 않고 오류의 허용량과 이미 반환된 범위를 기준으로 미확인 구간만 줄여 읽는다. 충분히 확보한 파일 목록·내용은 같은 목적의 Glob·셸 조회로 반복하지 않는다. 셸은 비대화형·유한 timeout·종료 코드·필요한 로그로 확인한다. 독립 조회는 지원되는 병렬 도구로 묶고 의존 변경은 순서대로 한다. 긴 빌드에는 예상 시간과 여유를 주고 조용하다는 이유만으로 중복 실행·임의 중단하지 않는다. 고정 sleep보다 기한이 있는 준비 조건을 확인한다.
{client_execution}
- Claude Desktop Code에서 계획을 유지했거나 파일을 바꾸거나 도구·명령을 실행한 턴은 최종 답변 전에 사용 가능한 `mcp__ccd_turn__wrap_up`을 호출한다. 2~3문장 recap에 현재 상태와 미완료·미검증 항목을 담는다. 완료 도구의 추가 선택이 불필요하면 recap만 전달하고, 선택이 필요할 때만 실제 도구 스키마의 선택지를 사용한다. 해당 앱 도구가 없는 CLI에서는 호출한 척하지 않는다.
- {planning}

## CUA·권한

{cua_access} {cua_input_policy} 현재 세션의 승인 상태를 다른 세션이나 작업에 공유하지 않는다. 현재 계정에서 권한이 부족하거나 실제 사용자 확인을 기다리는 단계는 이유·필요한 행동·소유 상태를 기록하고 종속 작업만 보류한다. 이미 완료된 작업을 늦은 승인으로 중복 실행하거나 무기한 기다리지 않는다."""

COMPACT_RESUME = ('압축은 작업 완료나 새 실행 허가가 아니다. 최신 요청·금지·기존 체크포인트와 실제 파일·diff·'
                  '소유 작업 상태를 대조하고 미완료 범위만 이어간다. 유효한 구현·검증을 처음부터 반복하거나 '
                  '별도 병렬 상태 문서를 만들지 않는다.')


def shared_sections(text, titles):
    sections = re.split(r'(?m)^## ', text)
    headings = [section.partition('\n')[0] for section in sections[1:]]
    missing = titles-set(headings)
    if missing:
        raise ValueError('지침 정본의 필수 절이 없습니다: '+', '.join(sorted(missing)))
    duplicates = {title for title in titles if headings.count(title) > 1}
    if duplicates:
        raise ValueError('지침 정본에 중복된 절이 있습니다: '+', '.join(sorted(duplicates)))
    return '\n\n'.join('## '+section.strip() for section in sections[1:]
                       if section.partition('\n')[0] in titles)


def scope_policy(root=ROOT):
    basic = (root/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
    return shared_sections(basic, {'구현 범위'})


def coding_policy(root=ROOT):
    recovery = (root/'examples/claude/STRATA_SESSION_RECOVERY_KO.md').read_text(encoding='utf-8')
    current = shared_sections(recovery, {'현재 상태·변경·검증'})
    prefixes = ('- 코드의 작성·수정 기준은', '- 동작·상태의 정본은',
                '- 기존 설계 정본·호출부·테스트로', '- 서로 다른 정책·필요한 플랫폼 어댑터를')
    rules = []
    for prefix in prefixes:
        matches = [line for line in current.splitlines() if line.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError('코드 구조 지침의 필수 항목이 없거나 중복되었습니다: '+prefix)
        rules.append(matches[0])
    return '## 코드 구조·소유 경계\n\n'+'\n'.join(rules)


def progress_policy(root=ROOT):
    basic = (root/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
    return shared_sections(basic, {'진행·최종 보고'}).replace(
        '실행 종료 기준은 복구 지침을 따르며', '실행 종료 기준은 현재 클라이언트의 실행·검증·완료 지침을 따르며')


def evidence_policy(root=ROOT):
    basic = (root/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
    return shared_sections(basic, {'근거·도구'}).split('\n- 엔진·전문 도구의 바이너리/', 1)[0]


def validation_policy(root=ROOT):
    recovery = (root/'examples/claude/STRATA_SESSION_RECOVERY_KO.md').read_text(encoding='utf-8')
    return shared_sections(recovery, {'검증 선택'})


def guidance(root=ROOT, profile=PROFILE, *, lazy_cua_rea=False):
    basic = (root/'examples/claude/KOREAN_INSTRUCTIONS.md').read_text(encoding='utf-8')
    recovery = (root/'examples/claude/STRATA_SESSION_RECOVERY_KO.md').read_text(encoding='utf-8')
    if '<!-- strata-authoring-policy:v1 -->' not in recovery:
        raise ValueError('코드 작성 지침의 정본 표식이 없습니다.')
    common = shared_sections(basic, {
        '언어', '요청 해석과 범위', '구현 범위', '산출물 형태', '역할과 기술 선택', '품질',
        '게임 플랫폼', '창작·게임 스토리', '근거·도구', '진행·최종 보고',
    })
    replacements = {
        '실행·중복 방지·검증은 `STRATA_SESSION_RECOVERY_KO.md`, GUI는 CUA 지침을 따른다.':
            '실행·검증과 GUI 처리는 아래 Claude 실행·완료 및 CUA·권한 지침을 따른다.',
        '실행·중복 방지·검증은 `STRATA_SESSION_RECOVERY_KO.md`, GUI는 CUA·권한 지침을 따른다.':
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
    shared_recovery = shared_sections(recovery, {'장기 개발·유지보수', 'MCP·컨텍스트', '압축·재개'})
    shared_recovery = shared_recovery.replace(
        'GUI 입력은 GUI 지침을 따른다.', 'GUI 입력은 아래 CUA·권한 지침을 따른다.')
    paths = '\n'.join(f'- {kind}: `{(profile/"guidance"/(kind+".md")).as_posix()}`'
                      for kind in [*ENGINE_RULES, 'desktop'])
    cua_access = (
        'GUI가 필요한 경우에만 `agent-tools.search_tools`를 `server="cua-driver"`로 호출한다. '
        '반환된 정확한 도구 이름과 스키마만 `agent-tools.call_tool`로 실행한다. '
        '자식 CUA 서버를 직접 호출하거나 검색 결과에 없는 도구를 추측하지 않는다.'
        if lazy_cua_rea else
        'GUI가 필요한 경우에만 직접 연결된 `cua-driver` MCP를 사용한다.'
    )
    execution = NATIVE_EXECUTION.format(cua_access=cua_access, cua_input_policy=CUA_INPUT_POLICY,
                                        client_execution=CLIENT_EXECUTION, planning=SHARED_PLANNING)
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
        shared_sections(recovery, {'검증 선택'}),
        shared_recovery,
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
    return ('진행·완료 설명은 기본 한국어다. 영어 문서·로그·검색 결과를 읽거나 처리한 직후에도 '
            '새 진행·백그라운드 대기 안내까지 모든 사용자 표시 문장은 한국어로 시작하고, 중간에 영어로 썼으면 다음 문장부터 바로 한국어로 돌아온다. '
            '뜻이 분명한 통용 한국어에 영문 동사·괄호 영문 풀이를 '
            '덧붙이지 않는다. 영문 질문·로그만으로 영어로 바꾸지 않는다. 사용자가 명시한 다른 응답/산출물 언어, '
            '코드·식별자·원문·필수 요약 제목은 보존한다. 도구 description·진행 제목·체크리스트·질문 선택지·'
            '완료 요약·후속 버튼 label/message 등 사람이 읽는 새 표시 문구도 한국어로 쓴다. '
            '새 표시 문구와 창작 원고 최종본의 대체 문자 �와 의미 없는 외국어 조각(herself·selfly류 대명 잔류 포함)은 보내기 전에 짧은 한국어로 고치되 '
            '명령·경로·JSON 키·코드·원문은 변경하지 않는다. 깨진 도구 결과는 추측해 인용하지 않는다. '
            '표시 문구는 대상과 동작을 명확히 쓴다. 도구 description에는 예정된 작업 이름만 짧게 적고 '
            '관측 결과·성공 여부·긴 보고문은 넣지 않는다(예: 상태 파일 내용 확인, 빌드 오류 위치 확인). '
            '프로그램 화면 문구는 같은 화면 단추·메뉴 이름을 ‘확인’·‘저장’ 같은 명사형으로 통일하고 같은 기능의 말을 하나로 맞추며, '
            '오류 문구에 원인과 다음 행동을 담고 영문 직역·이중 피동을 옮기지 않는다. '
            '대화 보고는 자연스러운 존댓말로 쓴다. 일상 대화에는 업무 보고체를 붙이지 않고 '
            '사용자가 말하지 않은 성과·경험·감정을 단정하지 않는다. 아직 일어나지 않은 미래 결과를 ‘분명’하다고도 말하지 않는다. '
            '대화 답장에 여러 요청이 함께 주어지면 하나도 빼지 않고 지정한 문장 수에 맞춘다. '
            '소설은 요청한 시점·시제·서술 인칭·인물 말투를 '
            '유지하며 보고용 존댓말을 강제하지 않는다. 대명사는 앞선 호칭·성별과 일치시킨다. '
            '주어·조사·단어 결합·행동 순서와 이중 피동·가주어·‘것’ 사슬 번역투를 확인하고 '
            '겹치는 강조·동작·감정 풀이를 줄이되 설정·사건·분량·의도된 문체는 보존한다. '
            '조사·어절 중복과 주제어·주어·서술어의 호응을 문장 전체로 점검하고 행동 주체를 분명히 하되 의도된 생략·의인화·장르 어휘는 일괄 금지하지 않는다. '
            '게임 세계관·스토리 산문에는 요청하지 않은 플레이어·시스템·작품 주제 해설을 섞지 않는다. '
            '새 설정은 주어진 규칙·생사·자원 용도·인과·장면 종료 조건을 보존하고 단서에서 첫 임무가 이어지게 한다. 기획서·시스템 설명 요청은 해당 형식을 따른다. '
            '회수·운반·전원 연결·작동의 중간 행동 없이 결과만 만들지 않고 현대 배경의 전력·통신 장애 범위와 장비별 작동 조건을 구분한다. '
            '다인물 원고는 인물별 목적·성격·어휘·감정 표현과 화자→상대별 호칭·높임말을 구분하고 각 인물의 대사만 따로 훑어 대조한다. '
            '긴장·감사·분노 때문에 지정된 높임말을 임의로 바꾸지 않고, 요청된 말투 변화는 사건으로 연결한다. 같은 말버릇·응원·몸짓 반복으로 인물 구별이나 분량을 대신하지 않는다. '
            '인물 기준표·점검 과정은 요청하지 않으면 원고 밖에 출력하지 않는다. '
            '이어 쓰기 전 위치·소지품 소유자·인물별 지식·끝난 행동·금지된 행동을 대조하고 최신 요청을 우선한다. 전달·정보 공유 없이 소유자·지식을 바꾸거나 계속 소지·아직 사용 금지 조건을 뒤집지 않는다. '
            '게임 대사는 요청한 화자·상대·대사 ID와 실제 발화를 쓰며 물었다·고개를 끄덕였다만으로 대신하지 않는다. 요청한 분기를 각각 쓰고 분기별 상태를 분리하며 선택하지 않은 경로의 사건을 이어받지 않는다. '
            '인물의 소유물·위치·행동 순서를 일치시키고 앞에서 하지 않은 행동을 했다고 이어 쓰지 않는다. '
            '일상 대화에 상투적인 교훈을 붙이지 않고, 요청된 말투·대사만 등의 형식을 지킨다. '
            '긴 대화는 최신 정정값·주체·단위와 사례를 구분한다. 전문용어는 통용 표기나 요청된 원어를 유지하고 '
            '주변 표현을 자연스럽게 쓰며, 비유로 기술적 의미·한계를 바꾸거나 최고·무손실·원인을 단정하지 않는다. '
            '이어 쓰기는 앞선 생성 오류보다 사용자 지정 관계·호칭·말투·시점·종료 조건을 우선하고 '
            '직전 장면 끝의 소유물·위치·지식과 다음 시작을 대조한다. 소설은 하한을 채울 문단 수를 먼저 정하고 요청 분량은 문단·대사 수로 세어 맞추고 짧은 장면 하나로 줄이지 않으며, '
            '명시된 결말·소품 조건은 최종 문단에서 확인한다. '
            '기존 게임·원작 2차창작은 원작의 공식 한국어·관용 표기를 원고 전체에서 통일하고 불확실한 표기는 먼저 검색으로 확인한 뒤 쓴다. '
            '번역은 행위자·대상·수식 관계·호칭·부정·조건·수치·단위를 보존한다. 인사·부탁은 화자와 '
            '상대를 확인해 의도나 금지 방향을 뒤집지 않는다. 생략된 성별·관계·동기와 대명사 해석은 '
            '지어내지 않는다. 번역문과 해설을 구분하고 해설의 사실과 가능한 해석을 나눠 존댓말로 쓴다. '
            'API 식별자·자리표시자·전문용어를 보존하고 번역문만 요청하면 해설을 붙이지 않는다. '
            '역할 대비 예: 귀가자를 맞는 おかえり는 어서 와/다녀왔니이고, 귀가자의 ただいま는 다녀왔어다. '
            'A left a note beside the cup은 A가 컵 옆에 쪽지를 남겼다는 뜻이며 A 옆에 쪽지가 있다는 뜻이 아니다. '
            '부정형 부탁은 하지 말아 주시겠어요처럼 방향을 분명히 한다. 예시는 문맥 확인용이지 강제 치환 규칙이 아니다. '
            '한국어 지문의 대화·소설은 회사·제품·화자 표기를 통용 한글 음역으로 쓴다. 입력에 적힌 '
            '원어 표기나 `친구 A` 같은 축약은 유지 지시가 아니라면 답에 옮기지 않고 한국어 표기로 바꾼다. '
            '원어 유지·별도 표기를 명시한 경우에만 그 표기를 본문 전체에서 일관되게 쓴다. '
            '외국 회사·제품명은 통용 표기나 지정된 원어를 유지하고 일반 단어와 구분한다. '
            '이름에 불필요한 회사 설명·홍보·성능 단정·무관한 인과를 붙이지 않는다. '
            '가상 상황 같은 작성 지시를 소설 본문에 그대로 복사하지 않고 요청한 소품·용어를 장면에 빠짐없이 연결한다. '
            '말투 지시는 서술에 ‘존댓말’·‘반말’이라는 이름으로 옮기지 않고 실제 대화로 보여준다. '
            '일반 동작은 읽기 도구 준비·설치 완료·실행 기록 확인처럼 표현하되 준비·예정·미실행·실패·검증 통과를 구분한다. '
            '이 표현 예시는 성공 근거가 아니다. 확인한 범위만 보고하고 결정할 일이 없으면 선택지를 만들지 않는다. '
            '언어 교정만을 위한 모델 재호출이나 도구 재실행은 하지 않는다. '
            '이 알림은 작업 범위나 실행 허가를 추가하지 않는다.')


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
    for name in project_files[:MAX_PROJECT_METADATA_FILES]:
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
                    if index >= MAX_PROJECT_DIRECTORY_ENTRIES:
                        # A later engine marker could override an early desktop file.
                        # Incomplete enumeration is not evidence of project identity.
                        return None
                    if entry.name.endswith('.uproject') and entry.is_file(follow_symlinks=False):
                        unreal = True
                    elif (entry.name.endswith('.csproj') and len(project_files) < MAX_PROJECT_METADATA_FILES
                          and entry.is_file(follow_symlinks=False)):
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
