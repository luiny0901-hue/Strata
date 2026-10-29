# Strata 클라이언트 공통 설정 확인 (2026-10-28)

Claude Code CLI·Claude Desktop Code·Codex가 같은 모델을 선택해도 모든 앱 설정이 자동으로 복제되지는 않는다. 모델 기능은 OpenCodex 공급자가 공유하고, MCP 실행·지침·권한·압축·완료 표시는 각 클라이언트가 소유한다. 다른 모델을 선택했을 때의 설정까지 Strata 값으로 덮어쓰지 않는다.

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
