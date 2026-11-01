# Strata 클라이언트 공통 설정 확인 (2026-10-28)

Claude Code CLI·Claude Desktop Code·Codex가 같은 모델을 선택해도 모든 앱 설정이 자동으로 복제되지는 않는다. 모델 기능은 OpenCodex 공급자가 공유하고, MCP 실행·지침·권한·압축·완료 표시는 각 클라이언트가 소유한다. 다른 모델을 선택했을 때의 설정까지 Strata 값으로 덮어쓰지 않는다.

아래 262K 값은 2026-10-28의 관측이다. 2026-11-01 현재 서버·모델 카탈로그는 1,048,576토큰, Claude 저장 압축 창은 1,000,000, Codex 저장 압축 시작점은 943,718, 기본 출력 상한은 32,000이다. 새 관측과 자율 작업 범위는 문서 마지막 절을 따른다.

## 적용한 공통 값

| 항목 | 현재 Strata 기준 | 적용 범위 |
| --- | --- | --- |
| 모델 | `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs` | 해당 모델의 공급자 정보 |
| 모델 창 | 262,144토큰 | Claude 공통 설정·OpenCodex 모델 정보·Codex 카탈로그 |
| 기본 출력 한도 | 32,000토큰 | Claude env·OpenCodex 모델별 `modelMaxOutputTokens` |
| 기본 추론 | Medium | 저장 기본값, 현재 화면 선택의 증거는 아님 |
| 실제 추론 단계 | Low·Medium·High | 기존 Strata 예산 3,072·4,096·8,192 유지 |
| 입력 | 텍스트·이미지 | 현재 모델 정보에서 확인, 모든 모델에 강제하지 않음 |
| 일반 MCP | `agent-tools` | Claude·Codex, 필요한 CUA·REA·웹 검색만 호출 |
| 유지보수 MCP | `strata-maintenance` | 기존 소유 프로젝트 `C:/Users/luiny/Strata`의 로컬 설정에만 등록 |
| Codex MCP 호출 제한 | 660초 | 기존 디스패처 600초 처리·취소 결과를 먼저 끊지 않게 여유 확보. 완료된 호출을 추가로 기다리지 않음 |

출력 한도가 생략된 Codex 요청은 이전에 일반 기본 8,192와 추론별 여유량 계산에 의존했다. 설치된 실제 Anthropic 어댑터의 Low/Medium/High 요청 구성은 변경 후 모두 32,000을 전달했다. 공급자 업데이트는 살아 있는 관리 API의 기존 단일 공급자 POST를 사용했다. 현재 버전의 PATCH/`models set`에는 max-output 항목이 없어, 최신 Strata 공급자의 나머지 필드를 보존한 채 제출했다. 전체 OpenCodex 설정 PUT·npm 설치 소스 수정·프록시 재시작은 하지 않았다.

이 값은 요청별 출력 기본값이다. 추론과 답변은 총 출력 한도를 공유한다. 작은 명시적 출력 한도는 OpenCodex의 기존 Anthropic 추론 여유량 계산 때문에 커질 수 있다. 1,200을 요청한 검사에서는 Low/Medium/High가 각각 12,288/16,384/24,576으로 구성됐다. 이 외부 어댑터 동작을 이번 변경으로 고쳤거나 모든 한도를 동일하게 강제했다고 보고하지 않는다.

## 앱별로 다른 값

- Claude용 `/v1/models`는 현재 Strata에 Low·Medium·High 지원, xhigh·max 미지원, 입력 262,144를 반환한다. 여기의 `max_tokens`는 OpenCodex 구현상 null이며 Claude의 실제 출력 기본값은 기존 env 32,000을 사용한다. `/api/models`와 기존 클라이언트 export에는 `maxOutputTokens`/`maxTokens` 32,000이 전달됨을 확인했다.
- Codex 카탈로그는 OpenCodex가 합성한 Max·Ultra도 표시한다. 모델의 추가 고유 추론 단계와 구분해야 한다. 이전 [추론 매핑 점검](CODEX_STRATA_REASONING_20261028_KO.md)의 한계를 유지하며 UI를 강제로 편집하지 않았다.
- Claude의 `autoCompactWindow=262144`는 내부 응답·압축 버퍼를 포함하는 창이다. Codex는 모델 창 262,144, 유효 비율 95%, 압축 시작점 235,929를 사용한다. 서로 의미가 다른 값을 숫자만 같게 바꾸지 않았다. 입력 262K와 출력 32K를 동시에 넣을 수 있다는 뜻도 아니다.
- 사용자 지침은 보존하고 Codex의 `AGENTS.md`에서 같은 한국어·요청 해석·산출물·품질 정본을 필요한 작업에만 읽게 연결했다. Claude의 훅·내장 완료 도구는 다른 앱에 복제하지 않는다. 전역 모델 선택·추론 선택·권한·다른 MCP는 보존한다.
- 유지보수 MCP는 Codex에서도 프로젝트 전용이다. Claude에서 꺼 둔 유지보수 서버를 새로 연결할 때 활성화하지 않는다. 각 앱의 이후 on/off·신뢰·승인은 그 앱에서 관리하며 앱 간 지속 동기화나 자동 승인을 제공하지 않는다. Codex의 프로젝트 설정은 [신뢰된 프로젝트에서만 로드된다](https://learn.chatgpt.com/docs/extend/mcp).

## 적용·재설치·다른 클라이언트

기존 Claude 연결을 먼저 준비한 뒤 서버 PC에서 실행한다. Python 3.11 이상을 사용한다.

```bat
setup-claude-opencodex.bat clients
setup-claude-opencodex.bat clients --check
```

Linux/macOS 진입점은 `./setup-claude-opencodex.sh clients`와 `clients --check`다. 이번 검사는 Windows에서만 수행했다. 모델 API 값을 바꾸지 않고 다른 PC의 로컬 Codex MCP·지침만 연결하려면 그 PC에 준비된 Claude MCP 설정을 기준으로 `clients --codex-only`를 실행한다. 이 옵션은 원격 모델 연결 주소·계정 설정을 대신 구성하지 않는다.

설정기는 `tools/strata_client_settings.py`를 사용한다. 모델 정보는 실제 Strata health와 기존 Claude 출력/기본 추론 설정에서 가져온다. Codex 등록은 그 PC의 기존 Claude 실행 경로·env에서 만든다. 설정 블록을 사용자가 고쳤거나 같은 이름의 다른 MCP가 있으면 보존하고 중단한다. 백업·소유 해시는 사용자 프로필에만 저장한다. 반복 실행 시 변경 파일 0개를 확인했다. `--check` 및 기존 `doctor.client_settings`는 저장된 설정만 검사하며 현재 UI·실제 압축 성공을 증명하지 않는다.

추가 앱은 기존 OpenCodex `ocx export --client <지원 앱>` 경로를 사용한다. Pi 내보내기에서 텍스트·이미지, 컨텍스트 262,144, 출력 32,000, reasoning=true를 확인했다. 목적 앱 형식에 추론 단계 목록이 없으면 세부 단계까지 자동 표기된다고 가정하지 않는다. MCP·지침은 해당 앱의 로컬 설정으로 따로 연결해야 한다. 모델 카탈로그를 읽는 앱도 캐시를 갱신하거나 재시작해야 하며, [Codex의 카탈로그는 시작 시 로드된다](https://learn.chatgpt.com/docs/config-file/config-reference).

## 검증 범위와 시도 기록

- 초기 전용 검사 8개 통과. 이후 유지보수 비활성화·호환성 처리를 추가한 관련 검사 11개(전용 9개와 기존 Claude 설정 2개) 통과. 외부 PC의 로컬 전용 경로 검사를 추가한 최종 **12개(전용 10개·기존 2개), 0.645초 통과**를 `final-tests.txt`에 보존했다. 최종 doctor는 Claude·Desktop 저장 연결 및 공통 설정 검사를 모두 통과했다.
- 설치된 실제 OpenCodex 어댑터로 요청 구성 6건을 검사했다. 네트워크 모델 생성은 하지 않았다. 기본 32K와 작은 명시적 한도의 기존 여유량 동작을 구분해 기록했다.
- 첫 MCP 검사는 CUA/REA 전용 `ChildServer`를 다른 서버 이름으로 재사용해 `invalid configured MCP server`로 실패했다. 이후 표준 stdio initialize/tools/list로 확인했으며 Codex의 agent-tools 3개, 프로젝트 유지보수 9개, 정상 종료를 확인했다. GUI 입력·역분석·검색·재시작 도구는 실행하지 않았다.
- `/v1/models/<Desktop alias>` 개별 조회는 404였다. 지원되는 목록 조회 `/v1/models`에서 현재 Strata의 기능 표기를 확인했다.
- Codex 네이티브 CLI가 새 설정을 파싱하고 agent-tools 활성 등록을 표시했다. 기존 다른 MCP 등록을 보존했다. 운영 폴더의 기존 BAT 전달 경로에서 `clients --check`도 통과했다.
- 현재 Desktop/Codex 화면의 선택·새 MCP 호출·262K 압축·성능/품질 비교·다른 OS·외부 PC 실제 연결은 이번에 검증하지 않았다. Codex를 재시작한 뒤 Strata를 다시 선택하고 새 세션에서 MCP를 확인한다. Strata·OpenCodex·Claude Desktop의 실행 중 작업은 재시작하지 않았다.

실행 근거: `C:/Users/luiny/Strata-data/diagnostics/client-settings-20261028/`. 커밋·푸시는 하지 않았다.

## 2026-11-01 자율 작업 점검

연결과 작업 루프는 준비되어 있지만, 권한 생략·큰 컨텍스트·HTTP 200만으로 완전 무인 개발을 보장하지 않는다. 도구 실행은 클라이언트가, 추론은 선택된 모델이 담당한다. 명세 해석·설계 판단·회귀 검증·외부 승인·실기 시험은 실제 작업별 근거가 필요하다.

### 확인된 상태

- Windows 11, Claude Code CLI `2.1.308`, Codex CLI `0.166.0-alpha.5.1`, OpenCodex 서비스 `2.92.0`을 확인했다. OpenCodex와 실제 Strata 모델 health는 준비 상태였다. GPU는 모델을 올린 RTX 3090 Ti, 모델은 Qwen3.8 Flash Next Unsloth UD-IQ4_XS다. 정밀도·모델·추론 단계·GPU 설정은 변경하지 않았다.
- Claude Desktop Code의 저장 게이트웨이는 OpenCodex이며 현재 유지보수 세션에서 도구 검색·파일 수정·명령 실행·검사 결과 수집을 수행했다. 이 사실을 장시간 무인 실행이나 전체 GUI 품질 검증으로 확대하지 않는다.
- Codex 설정의 `openai_base_url`은 `http://127.0.0.1:10100/v1`이나 기본 모델은 `gpt-6-astra`였다. CUA 읽기 전용 창 검사에서 ChatGPT 데스크톱의 **현재 모드: Codex**와 열린 대화의 Strata→GPT-6 Astra 모델 변경 기록을 확인했다. 사용자가 선택한 모델이나 기존 대화를 임의로 바꾸지 않았다. 일반 ChatGPT 채팅 모드를 이 코딩 경로와 동일하게 취급하지 않는다.
- 보조 에이전트와 WebFetch는 별도 모델 계정의 사용량 정책으로 HTTP 429를 반환했다. Strata health 정상과 구분한다. 보호 설정 해제·계정 자동 전환·반복 재시도는 하지 않았다. 공개 검색 결과는 확보했으나 공식 원문 확인은 도구 오류로 미완료다.

### 개선과 적용 범위

- `tools/claude_code_guidance.py`의 `CLIENT_EXECUTION`을 Claude·Codex 지침 생성에서 공유한다. Codex는 복잡한 작업에서만 읽던 별도 문서에 의존하지 않고, 매 세션 기본 지침에 실제 도구 결과·필수 작업 완료·검사 수·취소·재시도 전 부작용 확인 기준을 받는다. Claude 전용 완료 도구는 Codex에 복제하지 않는다. 지침은 모델의 준수율을 보장하는 강제 실행기나 새 에이전트 루프가 아니다.
- `audit()`는 카탈로그 값보다 우선하는 `model_auto_compact_token_limit`을 실제 검사·보고에 사용한다. 0·음수·컨텍스트 이상·잘못된 형식은 정상으로 보고하지 않는다. 원래 카탈로그 값은 `codex_catalog_compaction_trigger`로 따로 남긴다.
- 공통 Codex 지침의 누락·중복·내용 차이를 `checks.codex_guidance`로 검출한다. 개인 지침은 보존한다. MCP 제한 시간은 숫자 형식과 기존 660초 기준을 검사해 문자열 비교 오류와 디스패처의 600초 제한 직전 종료를 막는다. 이 진단은 실제 도구 성공의 증거가 아니다.
- 저장된 기본 모델은 `codex_saved_model`·`codex_model_selection`으로 별도 보고한다. 다른 모델을 선택했다고 공통 모델 정보까지 덮거나 설정 불일치로 간주하지 않는다. 프로필·명령 인수·열린 대화의 선택은 여전히 별도 확인 대상이다.
- `--codex-only`를 실제 적용해 사용자 `.codex/AGENTS.md`와 소유 해시 `strata-clients.json` 두 파일만 갱신했다. 기존 설정 파일·모델 선택·권한·MCP 등록은 변경하지 않았다. 백업 영수증은 `~/.codex/backups/strata-opencodex-20261031T225057151774Z/files.json`이며 재적용은 변경 0개였다. 현재 열린 대화의 지침을 소급 교체하지 않으므로 새 Codex 대화에서 사용한다. Claude 지침 생성 소스는 갱신했으나 사용자 전역 Claude 지침의 별도 사용자 변경은 덮어쓰지 않았다.
- Strata·OpenCodex·Desktop을 재시작하거나 새 서비스·감시 루프·강제 자동 승인을 추가하지 않았다. 서버 엔진 코드는 변경하지 않았다.

### 검증

새 진단 회귀 검사 4개는 수정 전 실패 8건·오류 9건으로 누락을 재현했다. 수정 뒤 Python 3.14.7에서 `py -B -X utf8 -m unittest tools.test_strata_client_settings tools.test_claude_code_guidance -q` 40개, `py -B -X utf8 -m unittest tools.test_claude_opencodex_client tools.test_claude_maintenance -q` 106개가 모두 통과했다. 이는 CPU 계약 검사이며 GPU 성능이나 모델 판단 품질의 개선율이 아니다. 새 프로세스의 `tools/strata_client_settings.py --check`도 통과했다. 이미 연결된 유지보수 MCP는 재연결 전까지 이전 코드를 유지할 수 있다.

실제 Strata 생성으로 두 CLI에 같은 할인 계산 오류를 수정하게 했다. 각각 격리된 폴더와 원래 테스트 5개, 수정 금지 파일을 사용했으며 외부 게시·서비스 변경은 허용하지 않았다.

- **Claude CLI**: 처음에는 Desktop 자식 프로세스의 환경 변수를 상속해 `Not logged in`으로 종료 1, 파일 변경 없음이었다. 별도 시험 프로세스에서 Desktop 전용 `CLAUDE_*` 변수를 분리하고 기존 사용자 설정을 읽게 한 재검사에서는 종료 0·7턴·26.31초였다. 실제 테스트의 수정 전 2개 실패, 한 줄 수정, 수정 후 5개 통과를 확인했다. 이는 사용자 셸의 일반 Claude CLI에 로그인 장애가 있다는 뜻이 아니다. 운영 실행기나 전역 환경은 변경하지 않았다.
- **Codex CLI**: `--model strata/qwen3.8-flash-next-unsloth-ud-iq4_xs --sandbox workspace-write`를 해당 시험 실행에만 지정했다. 종료 0·116.86초였고 수정 전 실패 확인·한 줄 수정·수정 후 5개 통과를 완료했다. 샌드박스에서 `py`가 보이지 않아 설치된 Python 3.12.15의 경로를 찾는 데 많은 조회가 들었다. 완료된 셸 명령은 31개였다. 완전한 효율 개선이나 무인 작업 품질을 보장하는 결과로 보지 않는다.
- 부모 검사기도 두 결과를 각각 Python 3.14.7로 다시 검사해 5개씩 통과했고, 테스트 파일·보호 파일의 SHA-256은 전후 동일했다. 이 시간들은 샌드박스·실행 환경·탐색 횟수가 달라 성능 비교나 개선율로 사용하지 않는다.

### 계획·체크리스트 표시 (2026-11-01 추가 점검)

Claude Desktop Code의 작업 체크리스트는 앱 내장 `mcp__ccd_turn__update_plan`·`wrap_up` 도구이며 저장소 코드가 아니라 앱이 렌더링한다. 같은 세션에서 작업 시작 시 전체 목록 생성 → 단계별 갱신 → 종료 시 마감하는 흐름을 실제로 사용·확인했다. 나머지 경로에 계획 전용 도구가 있는지는 실제 질문으로 확인했다.

- 터미널 Claude CLI(headless): 모델 자기 도구 목록에 TodoWrite·계획 도구가 없고 없음 응답(self-report). Codex CLI: plan·todo 전용 도구 없음(읽기 전용 실행 2회). ChatGPT Desktop은 같은 Codex 지침을 쓰므로 별도 도구가 없다. 세 경로 모두 체크리스트 UI는 앱이 제공하지 않으며, 항목별 진행 표시는 답변 텍스트로만 드러난다.
- 모든 표면에 같은 기준을 넣었다: 계획 도구가 있으면 처음에 전체 목록을 만들되 처음에는 딱 하나만 진행 중이고 나머지는 대기로 둔다. 끝난 단계만 근거를 가지고 갱신하고 최종 보고에서 목록 상태와 실제 결과를 일치시킨다. 처음부터 모든 항목을 완료로 두거나 목록 만들기를 진행으로 보지 않는다. 도구가 없으면 호출한 척하지 않고 3단계 이상 작업에서 번호 진행 목록을 텍스트로 유지한다(`tools/claude_code_guidance.py`의 `SHARED_PLANNING`, Claude·Codex 생성기 공유. 지침은 준수율 보장이 아니다).
- Codex에는 `--codex-only`로 실제 적용(변경 2개, 백업 `~/.codex/backups/strata-opencodex-20261031T230844569092Z`, 재적용 0개, audit 통과). Claude 전역 지침은 이 worktree에서 `setup`을 다시 적용하면 main 체크아웃 기준 설치본보다 오래된 문구로 되돌아갈 수 있어 설정기가 거부했고, 전체 재생성 대신 설치된 `~/.claude/CLAUDE.md`에 빠져 있던 wrap_up 항목 복원과 계획 유지 항목 추가만 했다. 두 설치 지침 파일에 항목이 1회 존재함을 확인했고 관련 검사 40개 통과. 이후 어느 쪽 `setup`도 해시 불일치로 재확인을 요구한다.
- 미검증: 새 Codex·ChatGPT 대화에서 체크리스트 기준을 따르는지, CLI headless 도구 목록은 모델 자기 보고라 완전성은 보장하지 않는다. Claude Desktop의 체크리스트 렌더링 자체는 앱 소유이며 저장소 변경 없이 이미 동작 중이다.

### 기술 선택·성능 검증 기준 보강 (2026-11-01)

기존 Claude·Codex 설치 지침 모두 구현 편의보다 대상 기기의 성능·자원 기준을 우선하고, 알고리즘·자료구조·입출력 병목부터 확인하도록 되어 있었다. 이번에는 `examples/claude/KOREAN_INSTRUCTIONS.md`의 기존 `구현 범위` 절에 두 항목만 추가했다. Claude 생성기는 이 절을 포함하며 Codex 생성기도 `scope_policy()`로 같은 절을 직접 포함하므로 별도 정책 파일이나 모델별 설정을 만들지 않았다.

- 설계 시 핵심 흐름·대표/최대 데이터·동시 부하·지연/처리량/메모리 한도를 정리하고, 요구와 가정을 구분한다. 설계 전용 요청은 구현이나 실측을 한 것처럼 보고하지 않는다.
- 구현 시 같은 입력·기기·빌드·정밀도·부하로 정확성과 성능을 함께 비교한다. 캐시·초기 실행·측정 변동·긴 지연·최대 메모리와 전송/동기화 비용을 고려하고 정확도·보안·호환성을 낮춰 속도를 얻지 않는다. 효과 없는 복잡도를 남기지 않고 작은 무관한 수정에 벤치마크를 강제하지 않는다.

실제 적용: Claude CLI·Desktop Code가 사용하는 `~/.claude/CLAUDE.md`에 해당 두 항목만 기존 게시 함수로 백업·동시 변경 검사 후 삽입했다. 두 항목을 제거한 나머지가 원본 바이트와 일치함을 확인했다. 수동 수정된 설치본의 전체 재생성이나 소유 해시 덮어쓰기는 하지 않았다. Codex CLI·ChatGPT Desktop의 Codex 모드가 사용하는 `~/.codex/AGENTS.md`는 기존 `sync_codex()`로 갱신했다. 열린 대화·프로필별 추가 지침의 실제 반영은 별도이며 새 세션에서 읽는다. 일반 ChatGPT 채팅 모드까지 적용된다는 뜻은 아니다.

백업: `~/.claude/backups/strata-opencodex-20261101T062028047595Z`와 `~/.codex/backups/strata-opencodex-20261101T062028088463Z`. 재적용은 양쪽 모두 변경 0개, 저장 진단은 `configured=true`였다. `py -B -X utf8 -m unittest tools.test_claude_code_guidance tools.test_strata_client_settings -q`로 41개 검사를 통과했고 `git diff --check`도 통과했다. 생성 지침 전달·설정 보존 검사이며, 네 클라이언트의 새 실제 설계 작업이나 생성된 제품의 성능 비교는 이번에 실행하지 않았다. 지침 보강을 모든 작업의 최적화 보장으로 해석하지 않는다. 모델·추론 수준·서비스·권한은 변경하지 않았다.

현재 체크아웃의 진단 산출물(버전 관리 제외): [Claude 최종 영수증](../.strata-mcp/autonomy-check-20261101/claude-standalone-summary.json), [Codex 최종 영수증](../.strata-mcp/autonomy-check-20261101/codex-summary.json), [Claude 독립 검사](../.strata-mcp/autonomy-check-20261101/claude-standalone-tests.log), [Codex 독립 검사](../.strata-mcp/autonomy-check-20261101/codex-tests.log). 단순 계산 수정의 도구 왕복·검증 증거이며, 새 ChatGPT Desktop 대화에서 같은 수정을 끝내는 시험·장시간 작업·1M 압축 경계·재부팅 복구·다른 OS는 이번에 실행하지 않았다. 커밋·푸시하지 않았다.

### 262K·1M × ON·OFF 4상태 확인 (2026-11-02)

실행 진입(262K ON/OFF, `-on-1m`/`-off-1m`, managed ON/OFF)은 4상태 모두 존재하며, managed 모드에서는 supervisor가 READY마다 `--sync-client-context`로 실제 서버 한도(컨텍스트·출력·추론 단계)를 네 앱 투사값에 반영한다(`strata_server_supervisor.sync_client_context` → `strata_client_settings --sync-runtime`, 전환 왕복 검사는 클라이언트 설정 테스트의 1048576↔262144 케이스).

- 발견·수정 1: 오늘 01:26 기동분의 클라이언트 동기화가 실패로 기록돼 있었다. 원인은 운영 체크아웃(`C:/Users/luiny/Strata`)의 실행 사본이 세대 불일치(`strata_client_settings`은 신규, `claude_code_guidance`는 `language_reminder` 이전)였던 것. 운영 사본 5개(위 두 파일 + `claude_opencodex_client`·`claude_code_support`·`claude_mcp_config` + `claude_mcp`의 searxng/exa)를 worktree 정본으로 맞췄고(백업 `~/.claude/backups/main-checkout-tools-20261102T015404Z/`), supervisor 형태 동기화 재실행으로 성공(투사 1건 보정, 백업 유지)을 확인했다. 내재 방지책으로 supervisor가 도구 쌍의 import를 검사하고 설치 소유자(path: hook/project)로 물러나는 폴백을 더했다(supervisor 테스트 28개).
- 발견·수정 2: 일반 터미널의 Claude CLI가 `unrecognized_model: strata/…`로 연결 실패였다(Desktop은 게이트웨이 wire 이름을 써서 무사). 동기화가 CLI 환경 모델 키들(`ANTHROPIC_MODEL` 등 7종 중 Strata를 가리키던 값)은 게이트웨이가 아는 wire 이름으로, `settings.model`은 공급자 ID로 유지하도록 `sync_context`를 고쳤다(설정 테스트 24개, 일반 `claude -p` 기본 설정으로 exit 0 재현).
- 현재 상태 실측: 서버는 1M ON 로드(health), Desktop Code는 본 세션 정상, Codex CLI 기본 실행 종료 0, Claude CLI 격리 실행 종료 0. 262K/OFF 상태 자체의 첫 전환 실시는 이번에도 미실시(세션이 서버를 점유해 전환 대기).
- 남은 과제: 두 체크아웃이 같은 사용자의 `AGENTS.md`·`config.toml` 블록을 같은 소유자로 재적용하는 문제 — 지침 텍스트가 바뀐 뒤 `--codex-only`가 MCP 블록의 이전-값 보호에서 거부하므로(`audit.codex_guidance=false`, 앱 동작은 정상이며 블록 실제 생성자 확인 후 해시 재확인이 필요), 운영 코드를 한 소유로 통합한 뒤 재적용한다.

### Codex 저장 기본 모델 Strata 지정 (2026-11-01 저녁, 사용자 요청)

Codex CLI와 ChatGPT Desktop의 저장 기본 모델이 `gpt-6-astra`로 남아 있어 대화가마다 선택을 요구했다. 사용자가 "코딩 앱이 OpenCodex로 Strata에 바로 연결되어 있게 해달라"고 요청해 `~/.codex/config.toml`의 `model` 한 줄을 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`로 바꿨다(백업 `~/.codex/backups/manual-strata-default-20261101T110034Z/config.toml`). 경유 주소는 기존 `http://127.0.0.1:10100/v1`(OpenCodex) 그대로이고 다른 키는 건드리지 않았다.

검증: `--model` 인수 없이 실행한 `codex exec`이 종료 0·`model: strata/...` 표시·응답 OK였다(추론 수준만 `low`로 덮어쓴 짧은 시험). `clients --check`은 `configured=true`, 항목 11개 전부 true, `codex_model_selection: strata_selected`였다. 반영 범위는 새 Codex 세션과 ChatGPT Desktop 재시작 이후이며, 열려 있던 대화의 선택은 그대로다. Claude Code CLI와 Desktop Code는 이전부터 게이트웨이·env가 OpenCodex 기본이라 변경이 없다. 외부 PC의 통합 설치기는 기존 설계대로 그 PC의 모델 선택을 보존하므로 이 기본값 변경이 자동 반영되지 않는다.
