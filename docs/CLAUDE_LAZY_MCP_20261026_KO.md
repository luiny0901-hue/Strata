# Claude Code CUA·REA on-demand MCP 검증

## 적용 상태

2026-10-26에 이 PC의 Claude 공통 설정에 `agent-tools`를 적용했습니다. 설정기는 `~/.claude.json`의 관리 대상인 직접 `cua-driver`·`rea` 항목을 대체하고 `strata-maintenance`는 유지했습니다. 최신 적용 백업/영수증은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T190315845984Z`입니다. 다른 사용자 MCP와 프로젝트별 상태는 설정기의 소유권/동시 변경 감지 절차에 맡겼습니다.

`doctor` 결과는 연결·Strata 모델·Claude Desktop 게이트웨이·저장된 MCP 설정 8개 검사가 모두 통과했습니다. 저장 설정 진단은 `mcp_delivery.mode=on_demand_cua_rea`, `status=configured`, `runtime_status=not_verified`였습니다. 이후 새 Claude Desktop Code 세션에서 `/context`를 실행해 실제 MCP 목록을 확인했습니다. 화면에는 MCP 도구 95개, MCP 스키마 33.7k 토큰, 전체 컨텍스트 71.6k/196.6k가 표시됐습니다.

기존 직접 MCP 세션은 도구 318개와 MCP 스키마 98.5k 토큰이 표시된 상태로 보존했습니다. 새 세션의 관측값은 도구 223개 감소, MCP 스키마 약 64.8k 토큰 감소입니다(화면 표본 기준 약 65.8%). 두 화면은 서로 다른 대화라 통제된 A/B 측정은 아닙니다. 기존 대화에는 설정이 소급 적용되지 않습니다.

## 실제 카탈로그와 토큰 계산

당시 참고한 로컬 클라이언트 JSONC에서 활성화된 MCP만 사용해 `tools/list`를 실제 호출했습니다. CUA는 18개 도구(직렬화 69,826바이트), REA는 207개(229,067바이트)였습니다. 서버별 최초 실행과 카탈로그 조회는 CUA 403ms, REA 1,934ms였고 같은 디스패처 프로세스의 캐시 검색은 각각 0.2ms, 0.6ms였습니다. 프로세스 기동·카탈로그 준비 시간이지 전체 모델 작업 시간이 아닙니다.

같은 대표 사용자 문구와 Strata `/v1/messages/count_tokens` 비생성 API로 계산한 MCP 선언 비용입니다. 모델은 `qwen3.8-flash-next-unsloth-ud-iq4_xs`였고 생성 요청은 하지 않았습니다.

| 조건 | 노출 도구 수 | 입력 토큰 |
|---|---:|---:|
| 직접 CUA 전체 | 18 | 9,297 |
| 직접 REA 전체 | 207 | 48,396 |
| 직접 CUA+REA 전체 | 225 | 57,693 |
| 디스패처만 | 2 | 303 |
| 디스패처 + CUA 검색 결과 4개 | 6 | 2,792 |
| 디스패처 + REA 검색 결과 4개 | 6 | 1,006 |

이 입력 조건에서 전체 CUA+REA 선언은 기본 디스패처 선언으로 약 99.5% 줄었습니다. CUA 작업은 검색된 도구 스키마 4개를 포함해도 직접 CUA 전체보다 약 70% 적었고, REA 작업은 약 97.9% 적었습니다. 이 값은 토큰 계산 API의 대표 프롬프트 결과로, Claude Desktop의 실제 `/context` 표시나 완료 시간과 같다고 보장하지 않습니다.

항상 등록되는 `strata-maintenance`도 같은 모델·요청 조건에서 별도 계산했습니다. 도구 4개와 직렬화된 스키마 2,494바이트가 기준 요청 71토큰에 744토큰을 더했습니다(전체 815토큰). 도구별 단독 계산은 기준 요청을 포함해 353~506토큰이었습니다. 이 정도 비용으로 기존 상태 확인·재시작 영수증·취소 기능을 유지하므로 현재는 별도 검색 디스패처로 바꾸지 않습니다. 이는 Strata 토큰 계산 API 결과이며 Claude Desktop의 `/context` 실측은 아닙니다.

이전 Desktop 세션의 화면 표본은 전체 MCP 98,466토큰 중 CUA 9,975, REA 54,717토큰이었습니다. 그 표본을 기준으로 단순 대입하면 새 총량은 약 34,077토큰이지만, 현재 새 세션에서 확인한 값이 아니므로 예상치로만 봅니다. `strata-maintenance`와 기타 MCP 비용은 계속 남습니다.

## 동작과 한계

- 기본 설정에서는 `search_tools`와 `call_tool`만 먼저 보입니다. `search_tools`는 지정한 `cua-driver` 또는 `rea` 하나만 시작하고 최대 8개 도구의 설명/정확한 입력 스키마를 반환합니다. 선택하지 않은 서버는 시작하지 않습니다.
- 검색 결과로 반환된 정확한 도구 이름만 호출할 수 있습니다. 이미지와 구조화된 데이터는 자식 MCP 응답을 보존해 전달합니다. 검색어에는 `창 목록`, `화면`, `클릭`, `키보드`, `역분석`, `디컴파일` 같은 한국어 별칭을 지원합니다.
- 실제 CUA `list_windows`와 REA `list_cutter_sessions`를 디스패처의 stdio 경로로 읽기 전용 호출해 성공했습니다. 창 제목과 세션 세부는 출력하지 않았습니다.
- 취소 알림은 자식 MCP에도 전달합니다. 취소·시간 초과 시 작업이 이미 끝났을 수 있으므로 디스패처는 그 서버를 해당 세션에서 격리하고, 상태 확인 전 재호출하지 말라는 오류를 반환합니다. 지연 응답 테스트로 취소 전달과 격리를 확인했습니다.
- 지연 설정은 Claude 공통 권한에 읽기 전용 `mcp__agent-tools__search_tools` 규칙을 추가합니다. 이미 이 도구를 허용하는 서버별 사용자 와일드카드가 있으면 재사용하고 중복 규칙을 만들지 않습니다. 설정 영수증은 이 설정기가 직접 추가한 규칙만 소유하므로 원복 시 사용자 규칙은 보존합니다. `mcp__agent-tools__call_tool`은 설정기가 자동 허용하지 않습니다. `doctor`는 서버별 허용 패턴과 우선 적용되는 `ask`·`deny` 규칙을 확인하지만, 세션별 모드나 앱에 이미 표시된 승인창은 알 수 없습니다. 설정을 적용한 뒤 관찰한 기존 Code 세션에는 같은 `search_tools` 허용 확인이 계속 표시됐습니다. 이 세션은 설정 변경 전에 시작된 상태였으므로 새 설정이 실패했다는 증거로 쓰지 않습니다. 현재 열린 작업을 건드리지 않았고, 새 세션에서 설정 적용 여부를 검증하지 않았습니다.
- 단독 stdio 검증에서는 최초 카탈로그 조회가 CUA 0.4초, REA 1.9초였지만, 새 Code 세션의 첫 실제 REA 검색은 6분 이상 걸렸고 명확한 PE 도구 결과와 최종 답변을 확인하지 못했습니다. 앱 권한 대기·모델 추론·MCP 목록 조회 시간을 분리할 계측이 없어 원인은 미확정이며, 앞선 단독 측정치를 실제 첫 사용의 지연으로 간주하지 않습니다.
- 디스패처는 각 카탈로그 페이지를 최대 30초, 전체 탐색을 최대 90초로 제한하고 반복 커서를 즉시 거부합니다. 기존 100페이지 반복 경로가 이론상 수십 분을 기다릴 수 있어 추가한 안전 한계입니다.
- Windows 프로세스 표본에서 REA Node 프로세스 6개, 합계 작업 집합 약 1.85GiB를 확인했습니다. 각 프로세스가 기존 세션과 연결돼 있는지 또는 유휴 잔류인지 판별하지 못했으므로 강제 종료하지 않았습니다.

## 검증

- 당시에는 `tools.test_lazy_mcp_dispatcher`, `tools.test_claude_opencodex_client`, `tools.test_claude_code_client`, `tools.test_claude_code_guidance`에서 76개 검사를 통과했다. 이후 직결 클라이언트와 그 전용 검사는 제거했고, 현재 유지되는 회귀 검사는 `tools.test_claude_mcp_lazy_dispatcher`, `tools.test_claude_opencodex_client`, `tools.test_claude_mcp_rea_launcher`, `tools.test_claude_code_guidance`다.
- 변경한 Python 파일의 `py_compile` 통과.
- 새 Code 세션의 `/context` 표시를 실제 확인했습니다. REA 검색 호출은 실행됐지만 첫 호출이 6분 이상 걸렸고 후속 검색까지 이어져, 도구 이름과 최종 답변을 검증하지 못했습니다. 실사용 REA 검색은 `PARTIAL`입니다.
- 전체 코딩 완료 시간, GPU 부하 A/B, 컨텍스트 압축 이후 코드 수정 작업은 이번 검증에서 측정하지 않았습니다.
- 첫 GUI 검증 스크립트는 MCP의 `notifications/initialized`에 응답을 기다리는 하네스 오류로 멈췄습니다. 요청과 알림을 분리한 하네스로 다시 실행해 실제 stdio 경로를 통과했습니다. 첫 검색 질의도 PowerShell 파이프의 비 ASCII 인코딩 때문에 깨졌으며, UTF-8 처리로 다시 확인했습니다.

## 2026-10-26 새 Claude Code 세션 추가 관측

새 Code 세션에서 동일한 읽기 전용 REA 카탈로그 검색을 한 번 요청했습니다. MCP stdio 연결 두 개는 각각 728ms, 735ms에 완료됐습니다. OpenCodex의 현재 Claude Messages 관측 로그에는 이 요청이 2026-10-26 04:29:43에 Strata로 전달되어 `200`으로 끝난 기록이 있습니다: 총 6,545ms, 첫 출력 40ms, 입력 66,582토큰(캐시 입력 53,572토큰), 출력 189토큰입니다. 단일 짧은 응답 표본이며 벤치마크가 아닙니다. 같은 시점의 최근 12건은 성공 12건, 중앙 요청 시간 4,490.5ms, 중앙 첫 출력 112.5ms, 첫 출력 후 벽시계 기준 중앙 74.0tok/s였습니다.

UI를 나중에 확인했을 때 `agent-tools.search_tools` 권한 요청이 대기 중이었습니다 (`server=rea`, `query=decompile executable`, `limit=1`). 화면을 중간에 관찰하지 않았으므로 권한 요청이 처음 표시된 시각은 알 수 없습니다. 모델 응답은 로그상 6,545ms 안에 끝났으므로 앞서 추정했던 수분 단위 모델 지연은 이 요청의 로그와 맞지 않습니다. 작업공간 신뢰와 별개인 Claude MCP 도구 권한을 사용자가 승인하지 않아 실제 `search_tools` 호출은 시작되지 않았고, 따라서 앞서 추가한 90초 카탈로그 제한의 라이브 동작은 아직 검증하지 못했습니다. 이 시험은 `PARTIAL`로 유지합니다.

화면에서 모델이 요청한 것은 이 설정의 일반 MCP 도구 `agent-tools.search_tools`입니다. 이는 Claude 내장 `ToolSearch` 프로토콜과 별개이므로, 이전 기록의 내장 `ToolSearch` 미노출 결과와 모순되지 않습니다. 새 경로에서 모델이 검색 도구를 선택한 것까지는 확인했지만, MCP 서버 권한을 허용해 실제 호출 결과를 받기 전에는 런타임 성공으로 판정하지 않습니다.

설정 변경 후 당시 디스패처 구성을 사용한 단독 REA 검색을 한 번 실행했습니다. `search_catalog(server="rea", query="decompile executable", limit=1)`는 1.873초에 완료되어 `batch_decompile` 후보 하나를 반환했습니다. 실제 `tools/call`은 실행하지 않았습니다. 이 결과는 REA 카탈로그·디스패처의 단독 지연을 보여 주며 Claude Desktop의 권한 확인, 모델 응답, UI 완료 표시를 포함하지 않습니다. 따라서 당시 대기 중이던 Desktop MCP 승인과 6분 이상 지연됐던 앱 세션의 원인을 이 결과만으로 판정하지 않습니다.

## 2026-10-26 후속 확인: maintenance MCP와 Desktop 승인 분리

현재 `~/.claude.json`에 저장된 `strata-maintenance` 실행 항목으로 별도 stdio 검증을 했습니다. `initialize`에서 `strata-maintenance` 1.0.0을 반환했고, `tools/list`에 `environment_status`, `restart_strata`, `restart_status`, `cancel_restart` 네 도구가 나타났습니다. `environment_status`는 정상 응답으로 `ready=true`, `desktop_ready=true`, 모델 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, 컨텍스트 262,144를 보고했습니다. 시작·initialize·목록·상태 조회 묶음을 3회 재측정해 중앙 335.3ms(295.6~337.5ms)였습니다. 이는 MCP 실행기 자체의 로컬 지연이며 모델 생성이나 Claude 화면 호출 시간을 포함하지 않습니다. Claude Code 화면에서 이 도구를 호출했다는 뜻도 아닙니다.

같은 시점의 읽기 전용 Claude Desktop 화면에는 `agent-tools.search_tools`의 REA 카탈로그 조회(`server=rea`, `query=decompile executable`, `limit=1`) 승인창이 계속 표시됐고, 권한 모드는 `수동`이었습니다. 검색 도구는 실행되지 않았습니다. 폴더 신뢰, 저장된 `settings.json` 허용 규칙, 이미 열린 Desktop 세션의 MCP 승인·모드는 서로 다른 상태로 기록합니다. 새 세션 또는 사용자의 앱 내 승인을 거쳐 `search_tools` 결과를 받기 전까지 Desktop의 on-demand REA 호출은 `PARTIAL`/`UNVERIFIED`입니다. 이 환경 검증은 승인창을 대신 조작하지 않습니다.

## 복구

직접 CUA·REA MCP로 전환하려면 `setup-claude-opencodex.bat --direct-cua-rea`를 실행합니다. macOS/Linux에서는 `bash setup-claude-opencodex.sh --direct-cua-rea`를 사용합니다. 기본 설정과 `--lazy-cua-rea`는 on-demand 방식입니다. 디스패처 코드 변경은 실행 중 프로세스에 소급되지 않으므로 새 Code 세션에서 `/mcp`와 `/context`를 확인합니다.

## 2026-10-26 권한 재확인과 진단 범위

현재 사용자 `~/.claude/settings.json`에는 `defaultMode=bypassPermissions`와 정확한 `mcp__agent-tools__search_tools` 허용 규칙이 있습니다. 저장소에는 `.claude/settings.json` 또는 `.claude/settings.local.json`이 없고, `~/.claude.json`의 프로젝트 항목은 신뢰 승인 상태입니다. `agent-tools`와 `strata-maintenance`는 사용자 MCP 서버로 등록돼 있습니다. 이 값들은 파일에서 읽은 저장 상태이며 현재 열린 Desktop 세션의 실효 권한을 증명하지 않습니다.

2026-10-26 현재 Claude Desktop Code 화면은 권한 모드 `수동`이고, 새 Code 세션에서도 다음 요청이 실행 전 승인 대기로 남았습니다: `agent-tools.search_tools(server=rea, query=decompile executable, limit=1)`. 따라서 앞서 기록한 “이전 세션이 설정 변경 전에 시작돼서 승인창이 남았을 수 있다”는 설명은 이 새 세션의 관측을 설명하지 못합니다. 허용 규칙은 올바른 서버·도구 이름으로 저장돼 있지만, 이 화면에서 실제 검색 호출은 실행되지 않았고 왜 승인창이 나타나는지는 확정하지 못했습니다. 저장소 신뢰 승인도 MCP 호출 승인을 대신하지 않습니다.

로컬 MCP 서버의 `search_tools` 정의는 읽기 전용(`readOnlyHint=true`)이며 `requiresUserInteraction` 표기를 보내지 않습니다. `claude mcp list`에서도 `agent-tools`와 `strata-maintenance`가 `Connected`로 확인됐습니다. 다만 서버 스키마와 CLI 연결 상태만으로 Desktop 승인창의 내부 원인을 확정할 수는 없습니다. `claude doctor`는 설치된 native CLI 2.1.308에서 “No installation issues found”를 반환했지만, 현재 Desktop 세션의 권한 모드·대기창은 검사하지 않습니다. 따라서 CLI 설치와 MCP 연결은 확인됐고, Desktop의 실제 검색 실행은 여전히 `PARTIAL`/`UNVERIFIED`입니다. 승인 전에는 `search_tools`를 완료된 호출로 세거나 검색 결과를 가정하지 않습니다.

## 2026-10-26 새 PC 기본 설치값 정렬

새 PC의 기본 `setup-claude-opencodex`가 CUA·REA 전체 MCP를 미리 등록해 현재 PC의 on-demand 운영 방식과 달랐습니다. 기본 설치를 on-demand `agent-tools`로 변경하고, 전체 직접 등록은 명시적인 `--direct-cua-rea` 옵션으로 옮겼습니다. 기존 `--lazy-cua-rea`는 호환용으로 유지했습니다. 사용자 MCP와 `call_tool` 허용 규칙은 자동 추가하지 않습니다.

현재 PC 설정은 이미 on-demand이므로 실행 중 Desktop 세션을 건드리지 않도록 사용자 설정기를 다시 적용하지 않았습니다. 변경 후 `tools.test_claude_opencodex_client`, `tools.test_lazy_mcp_dispatcher`, `tools.test_claude_maintenance`, `tools.test_claude_code_guidance` 총 74개가 통과했습니다. 첫 테스트 실행은 기존 직결 기본값을 가정하던 6개 assertion에서 실패했으며, 기본값 변경에 맞춰 테스트를 직접 모드로 명시하거나 on-demand 기대값으로 수정한 뒤 전체 재실행이 통과했습니다. 라이브 `doctor`는 `ready=true`, `desktop_ready=true`, MCP 저장 모드 `on_demand_cua_rea`, native Messages 경로로 확인됐습니다. 이는 저장 설정·연결 상태이며 MCP 런타임은 `not_verified`입니다. Desktop 화면의 REA 검색 승인 대기는 그대로 남아 있습니다.

## 2026-10-26 Claude Desktop Code 우회 권한과 on-demand MCP 실사용 재검증

사용자가 Claude Code의 작업 중 승인 대기를 없애도록 명시적으로 요청했다. Claude Desktop 설정에서 `Allow bypass permissions mode`를 활성화했고, 현재 저장소 Code 세션의 하단 권한 모드가 `권한 무시`로 표시되는 것을 확인했다. 사용자 `settings.json`에는 이미 `defaultMode=bypassPermissions`가 있었으며 MCP 허용목록은 넓히지 않았다. 특히 `agent-tools.call_tool`의 전역 `allow` 규칙을 추가하지 않았다.

같은 실제 Desktop Code 세션에서 아래 MCP 경로를 각 1회 호출했다. 승인 팝업 없이 결과가 반환됐다.

- `agent-tools.search_tools`: `cua-driver`의 읽기 전용 창 목록 도구를 검색해 정확한 이름 `list_windows`와 `readOnlyHint=true`를 반환했다.
- `agent-tools.call_tool`: 검색된 `list_windows`를 정확히 한 번 실행해 창 17개를 확인했다. 창 목록만 읽었으며 클릭·키 입력·스크롤은 하지 않았다.
- `strata-maintenance.environment_status`: `ready=true`, `desktop_ready=true`, 모델 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, 컨텍스트 262,144, Strata `in_flight=0`을 반환했다. 재시작·파일 수정·설정 변경은 없었다.

이는 현재 Claude Desktop 세션의 모델 경로와 두 MCP 연결의 읽기 전용 호출이 우회 모드에서 동작한다는 실사용 증거다. 실제 CUA 클릭·입력, REA 파일 분석, 서버 재시작, Desktop 재실행 뒤 새 세션의 권한 모드는 이번 확인 범위에 포함하지 않았다. 따라서 모든 MCP 동작이나 재부팅 후 상태까지 검증됐다고 보지 않는다. Desktop `/context`는 이 세션에서 77.7k/196.6k였고 `MCP tools` 96개·33.9k 토큰을 표시했다. 이 수치는 앱 화면의 합계이며 전부 CUA·REA 스키마라고 단정하지 않는다.

우회 권한은 앱 설정과 현재 세션 모드에 적용된다. 권한 설정이 저장된 상태와 실제로 열린 세션의 상태는 구분해서 보고한다. 공식 Claude Code 문서도 이 모드가 권한 확인을 건너뛰는 고권한 모드라고 설명한다.
