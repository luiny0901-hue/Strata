# Strata·OpenCodex·Claude Desktop Code 유지보수

이 문서는 이 실행 환경 자체를 변경할 때만 읽는다. 일반 앱·게임 개발에는 추가 점검을 강제하지 않는다.

## 먼저 확인할 소유자

- `doctor`의 `effort_level`은 `~/.claude/settings.json`에 저장된 Low·Medium·High 기본값만 읽고, 상태를 `configured`·`missing`·`invalid`로 표시한다. `runtime_status=not_verified`는 열린 Desktop Code 세션이나 실제 요청에 적용된 추론 성능을 읽지 못한다는 뜻이다. 이를 현재 선택으로 단정하거나 `ready` 판정에 포함하지 않는다.

- 주 화면은 Claude Desktop의 Code이며, 3p 게이트웨이 프로필이 OpenCodex 10100을 선택한다. Desktop이 자체 주입하는 연결 주소·모델·15분 API timeout은 CLI의 env 값만 수정해서 바뀐다고 가정하지 않는다. `~/.claude/settings.json`의 한국어·권한·훅·지침과 `~/.claude.json`의 사용자 MCP와 프로젝트 전용 MCP는 로컬 Code 세션에서도 사용한다. `strata-maintenance`는 설정기를 실행한 Strata 저장소의 local scope에만 등록하며, 유지보수는 그 폴더의 새 Code 세션에서 진행한다. 일반 프로젝트에는 해당 서버가 없고, 유지보수 프로젝트에서 `/mcp`로 끈 상태도 설정 재적용 때 보존한다. 연결된 Git worktree는 Claude Code의 원본 저장소 프로젝트 설정을 공유한다. MCP stdio 서버는 Claude Code가 직접 실행하고, OpenCodex·Strata는 모델 API 요청을 처리한다. Desktop의 연결은 `%LOCALAPPDATA%/Claude-3p/configLibrary`와 OpenCodex의 기존 Desktop 관리 경로에서 변경한다. 다른 공급자·저장된 대화를 보존하고 비밀 값은 출력하지 않는다.
- OpenCodex 설치·서비스 소유 정보는 `~/.opencodex/service-state.json`, 공급자와 설정은 `~/.opencodex/config.json`이다. 설치 위치는 소유 정보에서 확인한다. 살아 있는 프록시의 설정은 기존 OpenCodex 관리 API/CLI를 사용해 해당 필드만 변경한다. `/api/config` 전체 PUT은 비활성이다. 실행 중 JSON 전체를 오래된 복사본으로 덮어쓰거나 npm 설치 파일을 직접 수정한 뒤 영구 패치라고 보고하지 않는다. 소스 수정은 해당 프로젝트의 AGENTS.md·구조 문서·기존 테스트를 따른다.
- 현재 측정한 빠른 연결은 Strata 공급자 `adapter:anthropic`과 `protocols.rollout.managedMessagesNative:true`다. 기존 관리 API와 계획 조회로 확인하며, 다른 공급자나 OAuth 옵션까지 묶어 바꾸지 않는다.
- 현재 PC의 Desktop 3p 프로필은 `toolSearchEnabled: true`이며, 실제 Code 세션의 Claude Code 내장 `ToolSearch`와 지연 도구 호출을 확인했다. 이전에는 이 프로필 값이 빠져 `ENABLE_TOOL_SEARCH=true`만으로 도구 검색이 노출되지 않았다. 현재 PC는 전체 CUA·REA 스키마를 미리 넣지 않는 `agent-tools` on-demand 디스패처를 사용한다. Claude Code가 도구를 찾을 때 `agent-tools.search_tools`에서 `cua-driver` 또는 `rea`와 작업에 맞는 검색어를 선택하고, 반환된 정확한 도구만 `agent-tools.call_tool`로 호출한다. CUA·REA 하위 카탈로그는 디스패처가 관리하고, Claude Code의 내장 ToolSearch는 사용자 MCP 스키마 지연 로드에 사용한다. 일반 프로젝트의 `/mcp`에는 `agent-tools`가, 유지보수 프로젝트에는 `strata-maintenance`도 표시되어야 한다. CUA·REA 자식 서버는 디스패처가 필요한 쪽만 시작하므로 프로젝트에서 별도 서버를 켜고 끄지 않는다. 직접 CUA·REA 등록으로 바꾸는 것은 사용자가 설정 모드를 바꾸라고 요청했을 때만 한다. 디스패처의 CPU 검사·실제 로컬 카탈로그·비생성 토큰 계산 결과는 `docs/CLAUDE_LAZY_MCP_20261026_KO.md`에 있다. 새 Desktop Code 세션의 `/context` 실제 절감량과 도구 호출은 해당 세션에서 별도 확인한다. 예전 `/context` 관측 318개 도구·약 98.5k 토큰은 직접 CUA·REA가 등록된 이전 세션의 수치이며 현재 세션의 비용으로 사용하지 않는다. REA 입력 스키마는 `compact`, 출력 스키마는 `off`로 유지한다.
- `environment_status`는 물리 메모리 여유량, Strata의 GPU/VRAM·RAM·모델 컨텍스트·동시성·마지막 요청 엔진 타이밍, tools·reasoning·cache 요청의 읽기 전용 경로 미리보기, OpenCodex 최근 Claude Messages 요청의 경로·응답시간 표본, OpenCodex request-pacing 상태를 보여준다. `/v1/status`에서 인증된 로컬 응답만 읽고, 정해진 숫자·문자열 필드만 반환하며 리다이렉트를 따르지 않는다. 응답은 256 KiB로 제한한다. GPU 메모리는 다른 앱과 공유되는 장치 전체 값이고 RAM·VRAM 어느 값도 작업별 추가 요구량이나 대용량 요청의 성공을 보장하지 않는다. `last_request_timings`는 Strata가 마지막으로 끝낸 요청이며 다른 클라이언트가 함께 사용하면 최근 Claude 요청과 자동으로 상관관계가 있다고 보지 않는다. `strata_activity`는 Strata에 전달된 실행·내부 대기 요청만 나타내며 OpenCodex가 아직 Strata에 전달하지 않은 대기열은 포함하지 않는다. 상태 API가 없거나 활동값이 유효하지 않으면 이전 `/slots` 조회로 대체하고 그 범위를 표시한다. `opencodex_request_pacing`은 페이싱 기능이 추적하는 대기·동시성만 표시한다. 설치된 OpenCodex의 managed native Messages 전송은 공통 `providerFetch`를 거치므로 설정된 `maxConcurrentRequests` 상한도 적용된다. 페이싱이 꺼져 있거나 `in_flight`가 누락되면 전체 요청 수는 알 수 없다. 이 값들은 전체 경로 유휴 증거로 단독 사용하지 않는다. 요청 표본은 최근 Strata 요청 최대 12건이며 Claude CLI와 Claude Desktop을 구분해 건수·중앙 응답시간·첫 응답 청크·decode 속도 표본을 표시한다. `first_response_chunk_ms`는 첫 upstream body chunk의 시각이지 첫 모델 토큰 또는 첫 답변 토큰의 지연이 아니다. `decode_rate_by_basis`는 OpenCodex generation-window decode 추정만 표시하며, 짧거나 예전 방식으로만 기록된 창은 측정 불가로 둔다. `request_output_tokens_per_second`는 프리필·추론·게이트웨이를 포함한 전체 요청 처리율이며 디코딩 속도가 아니다. 프롬프트·응답·헤더·요청 ID는 반환하지 않는다. 작은 최근 표본은 벤치마크가 아니며, 정책별 변환·검색·이미지 처리 결과를 미리보기 하나로 단정하지 않는다. 측정 근거는 설치의 `docs/CLAUDE_OPENCODEX_LATENCY_20261025_KO.md`에 있다.
- Strata는 기존 supervisor가 시작 프로그램의 실행기를 소유한다. `strata-maintenance` MCP의 `environment_status`로 프록시와 실제 모델 준비 및 Strata 슬롯 상태를 확인한다. OpenCodex 서비스 소유자는 `opencodex_service_status`가 기록된 Bun/CLI의 수동 `service status --json` 명령으로 확인한다. 이 도구는 토큰을 제외한 서비스 상태·PID·서빙 런타임만 반환하고 서비스를 바꾸지 않는다. 프록시의 캐시된 모델 목록만으로 서버가 실행 중이라고 판정하지 않는다. 재시작 때문에 두 번째 서버나 supervisor를 만들지 않는다.
- Strata 실행기는 템플릿에서 프로필을 다시 생성한다. 프로필을 변경하려면 실행기가 실제 참조하는 템플릿·생성된 JSON·현재 실행 설정을 확인한다. 서버 루트와 NVFP4 fork의 `serve/server.py`는 서로 다를 수 있으므로 통째로 복사하지 않는다. 모델·Pack·GPU·vram reserve·추론/출력/압축 값을 요청과 근거 없이 바꾸지 않는다.
- Claude 공통 설정은 `tools/claude_opencodex_client.py setup`이 관리한다. MCP 정본은 `~/.claude/strata-mcp.json`이며, 디스패처와 새 PC용 설정은 Claude 소유 파일을 사용한다. 생성 지침의 정본은 Claude 전용 `docs/CLAUDE_SELF_MAINTENANCE_KO.md`와 `docs/CLAUDE_*.md` 문서이며, `~/.claude/CLAUDE.md`·guidance는 생성물이다. 개인 규칙은 프로젝트 CLAUDE.md·개인 파일에 둔다. 설정 재적용 전후 diff와 백업 영수증을 확인한다. 다른 세션의 설정 변경이 감지되면 최신 파일을 읽고 병합하며 강제 덮어쓰기하지 않는다. `doctor`의 `mcp_delivery.status`는 저장된 direct/on-demand MCP 연결만 확인한다. 지연 모드의 `mcp_permissions.status`는 저장된 허용 규칙과 우선 적용되는 ask/deny 규칙을 확인하지만 기존 Desktop 권한창은 확인하지 않는다. 설정기는 실제 유지보수 MCP가 준비된 경우 읽기 전용 `environment_status`, `opencodex_service_status`, `restart_status`, `desktop_restart_status`의 개별 `allow` 규칙만 추가하고, `restart_strata`, `cancel_restart`, `agent-tools.call_tool` 규칙은 만들지 않는다. 실제 실행 승인은 현재 Claude Code 세션 모드, 프로젝트별 설정, Desktop 앱 확인의 영향을 별도로 받는다. `desktop_permission_mode`는 `settings.json`의 새 Desktop 세션 기본 모드만 보여주며, 폴더별로 기억한 선택이나 현재 세션 모드는 확인하지 않는다. MCP 및 권한 모드의 런타임은 `runtime_status=not_verified`로 둔다. `environment_status.ready`는 공통 경로, `desktop_ready`는 Claude Desktop 3p 게이트웨이까지 각각 나타내므로 새 PC 보고에서 두 상태를 구분한다.

설정기를 다시 실행할 때는 이전 상태에 저장된 Python 실행 파일이 존재하면 계속 사용한다. 새 PC이거나 기존 경로를 찾지 못한 경우 설정기를 실행한 Python을 기록한다. 의도적으로 바꾸려면 `STRATA_CLAUDE_PYTHON`을 지정한다. 명시한 실행 파일을 확인할 수 없으면 프로필을 변경하지 않고 실패한다.

## 컨텍스트와 MCP 진단

`doctor.context_window_policy`는 환경 변수 → 모델별 설정 → 공통 설정 순서로 저장된 압축 창을 확인하며 `full_model_window`와 `reduced_window`를 구분한다. 현재 창은 262,144, 응답 상한은 32,000이다. CLI 플래그·Desktop 주입값·이미 열린 세션 반영은 별도로 확인한다. `mcp_delivery`의 `additional_user_servers`와 `duplicate_direct_servers`로 관리 대상 외의 연결 및 CUA/REA 중복 직접 등록을 확인한다. 예전 소유 기록에 모드 표식이 없어도 관리 서버가 `agent-tools`면 실제 디스패처 경로·정본 경로·허용 규칙을 검사한다. 이 경우 `mode_inferred_from_managed_server=true`이며 실제 세션 호출 증거를 대신하지 않는다.

Desktop의 `ccd_*`·Claude Browser·terminal·scheduled-tasks는 앱이 제공하는 내장 도구이며 사용자 MCP 등록 목록과 다르다. 내장 도구 비용을 CUA/REA 디스패처 비용으로 계산하거나, `~/.claude.json`에서 지웠다고 사라졌다고 보고하지 않는다. 현재 모델에서 실제 지원하지 않는 ToolSearch를 지원한다고 표시하지 않는다.

## 선택형 자동 압축 서식

`anthropic_compact_summary: true`는 알려진 Claude Code 압축 요청에서 원래 대화·사용자 추가 지침·훅 문맥을 보존하고 간결한 내부 복구 요약 지침만 추가한다. 일반 요청과 알 수 없는 템플릿은 그대로이며, 출력 상한·추론 수준·262,144 창은 줄이지 않는다. 내부 설명은 영어를 기본으로 하고 제약은 원문으로 보존한다. 명시한 요약 언어·서식은 사용자 요청을 따른다. 일반 진행·최종 보고의 한국어는 유지한다.

현재 PC의 ON 템플릿과 생성 프로필에만 켰으며 기본 서버값은 꺼져 있다. 새 PC나 별도 NVFP4 fork는 해당 서버 코드 반영이 필요하다. 적용 범위·실측·되돌림은 저장소의 `docs/CLAUDE_COMPACTION_SPEED_20261027_KO.md`를 확인한다. 요약 시간의 한 관측을 전체 작업이나 모든 프로젝트의 보장 개선율로 해석하지 않는다.

## 선택형 OpenCodex 요청 로그 진단

`strata-maintenance.environment_status`는 기본 호출에서 기존 Strata·OpenCodex 상태만 조회하며 요청 로그용 CLI 프로세스를 시작하지 않는다. 요청 원인·지연을 확인해야 할 때만 `include_opencodex_requests=true`와 `request_window=15m` 또는 `1h`를 전달한다. 이 경로는 기록된 Bun/CLI 소유자를 사용해 Claude 표본 최대 12건을 읽으며 8초 제한과 stdout 128 KiB 스트리밍 상한을 적용한다. 허용된 시간·상태·effort·사용량 필드만 반환하고 ID·프롬프트·응답·헤더·추적 세부정보는 반환하지 않는다. `claude` 표면은 CLI와 Desktop을 묶으므로 시간대를 UI와 대조해야 한다. `close_reason=terminal`은 응답 본문 EOF만 뜻하고 `message_stop`이나 Desktop 완료를 증명하지 않는다. 이 선택형 로그 요약은 작은 최근 표본이며 벤치마크가 아니다. 구현 버전은 MCP `1.3.0`다.

## 적용 순서

요청 범위와 완료 조건을 확인하고 해당 소유자·실제 버전·현재 파일을 확인한다. 원본을 보존한 최소 변경을 준비하고 관련 검사만 수행한다. 변경을 저장한 사실, 새 프로세스에 반영된 사실, 실제 동작·성능 검증을 구분해 보고한다. MCP stdio 도구는 실행 시 소스 코드를 로드하므로 이미 연결된 세션은 소스 변경을 자동으로 다시 읽지 않는다. 도구 구현을 바꿨다면 MCP를 다시 연결하거나 새 Code 세션에서 도구 목록·버전을 확인한다. 이를 위해 Desktop·OpenCodex·Strata를 불필요하게 재시작하지 않는다. 한 번에 여러 설정을 무근거로 바꿔 최적화라고 부르지 않는다.

Strata 재시작이 필요한 경우 파일을 먼저 저장하고 작업 범위·완료/미완료·변경 경로·남은 검증을 checkpoint로 작성한다. MCP `restart_strata`에 고유한 operation_id와 같은 checkpoint를 전달하고 실제 ready 결과를 기다린다. 재시작은 기존 supervisor가 idle을 확인한 뒤 수행한다. 전달이 불확실하면 같은 ID로 `restart_status`를 조회한다. 다른 ID로 중복 재시작하지 않는다. 실패·취소는 완료가 아니며 실제 상태를 확인하고 남은 작업만 처리한다. 정지·취소 요청 뒤 늦은 완료 알림이 새 작업 권한이 되지 않는다.

대상별로 재실행 경로가 다르다. 모델 서버는 `restart_strata`, Desktop은 체크포인트 인계(`restart_desktop`)를 쓰고 supervisor 자체만 실행기 재시작으로 바뀐다. 사람이 실행기를 실행하면 explorer 별도 트리에 걸려 Desktop과 독립이다. 반면 에이전트가 supervisor를 다시 띄울 때는 Desktop Code의 도구 자식 트리 안(`Start-Process` 포함)에서 실행하면 안 된다 — 그 supervisor는 Desktop 종료 연쇄에 함께 종료된다. 분리 실행(예: WMI `Win32_Process.Create`로 실행기 배치를 직접 호출)을 사용하고, 띄운 뒤 8768 리스너 프로세스의 부모 체인이 Desktop 밖인지 확인한다. 두 재실행은 같은 작업을 이어 가기 위한 것이다: 서버 재시작은 한 요청 안에서 ready 결과를 받은 뒤 남은 작업을 계속하고(2026-10-27 실측), Desktop 인계는 재개 실행이 체크포인트를 계약으로 그 요청 안에서 미완료를 이어가며 재열기 후 같은 대화가 계속된다(같은 날 실측). 에이전트의 추론 스택이 supervisor에 달려 있어 supervisor 자체 재시작 직후에만 같은 요청 내 이어하기가 지원되지 않으며, 그 경우 변경은 다음 supervisor 시작부터 반영됨을 인계 기록에 남긴다.

OpenCodex 재시작·업데이트는 현재 Code 연결과 다른 진행 중 요청을 끊을 수 있다. 먼저 체크포인트를 프로젝트의 기존 작업 상태 문서에 저장하고 `opencodex_service_status`로 설치 소유자·상태·PID·`served_at`을 기록한다. 가능한 설정 변경은 기존 live 관리 경로로 적용한다. 사용자가 요청한 코드·설정 변경에 재시작이 필요하면 `environment_status.strata_activity.status`가 `idle`인지 확인하고, 별도 OpenCodex 클라이언트나 대기 요청이 없다는 근거도 확인한다. `opencodex_request_pacing`은 페이싱 적용 요청만 추적하며 페이싱이 꺼져 있거나 `in_flight`가 없으면 전체 OpenCodex 작업의 유휴를 증명하지 않는다. 이 경우에도 다른 클라이언트·대기 요청을 배제할 근거가 없다면 재시작을 미룬다. 조건을 확인한 경우 도구가 반환한 기존 서비스 소유자의 `service restart` 명령만 사용한다. 상태에서 소유자가 오래됐거나 충돌이 있으면 `repair`·재설치·승격 실행을 자동으로 시도하지 않는다. 재시작 뒤 같은 상태 도구와 `environment_status`로 서비스 준비·PID 또는 `served_at` 변화·모델 연결을 확인하고 후속 요청을 끝낸다. 전달이 불확실하면 같은 작업 상태와 런타임 식별자를 비교해 결과부터 확인하고, 이미 재시작됐을 수 있으면 다시 실행하지 않는다. 프록시를 직접 kill하거나 새 watchdog·별도 에이전트 루프로 대체하지 않는다. 확인할 수 없는 재개를 자동 보장했다고 보고하지 않는다. 실행 중 요청 여부를 확인할 수 없으면 재시작을 미룬다.

Claude Desktop 또는 내장 Claude Code 업데이트·재실행이 필요하면 작업 파일과 기존 작업 상태 문서에 체크포인트를 저장한다. 유지보수 범위에 필요한 정상 재시작이 이미 허용되었다면 같은 승인을 반복해서 요구하지 않는다. 창 닫기는 트레이에 숨기는 동작일 수 있으므로 정상 종료 메뉴로 끝내고 해당 Code/MCP 프로세스가 종료됐는지 확인한다.

Windows의 선택 기능인 Desktop 재시작 복구는 기존 Strata supervisor가 소유한다. 새 PC에서는 Claude Desktop Code 게이트웨이 연결을 먼저 마친 뒤 `setup-desktop-restart.bat`를 한 번 실행하고 평소 ON/OFF BAT로 Strata를 다시 시작한다. 추가 모델·상시 서비스·디버깅 포트는 설치하지 않는다. 설정은 `~/.config/strata/server-control/desktop-restart.json`, 거래 영수증은 기존 supervisor 상태 폴더의 `desktop/`에 저장한다. 설정 파일이 없으면 이 기능은 꺼져 있다.

재시작 전 `desktop_restart_status`를 인자 없이 호출해 외부 소유자의 `enabled`와 `current_session_id`를 확인한다. 인계 대기에는 별도 상한이 없고 거래 기한(`continuation_timeout_seconds`, 기본 24시간)까지 기다렸다가 조건이 성립한 뒤 잠시 안정되면 곧바로 종료한다. 그동안 트랜스크립트 기록이 15분 이상 멈춘 소유 세션은 중단·대기 상태로 보아 종료를 막지 않는다. 기한까지 조건이 성립하지 않아 실패하면 `error_code`로 원인을 가린다(원 턴 미완 `original_turn_unfinished`, 다른 세션 실행 중 `other_sessions_busy`). 이 ID는 호출한 Code 프로세스의 실제 부모 관계에서 읽으며 최근 대화나 Desktop의 `local_` ID를 대신 사용하지 않는다. 현재 프로젝트 안의 기존 작업 상태 문서에 요청 범위·완료/미완료·정확한 파일·남은 검증을 저장하고 `restart_desktop(operation_id, session_id, checkpoint_path)`를 한 번 호출한다. 수락 결과를 받으면 재시작 인계 중임을 짧게 보고하고 현재 턴을 끝낸다. 이 단계는 현재 턴에서 기다리지 않는 명시적인 인계이며 전체 사용자 작업 완료가 아니다. 같은 턴에서 상태를 계속 조회하거나 새 ID로 재제출하면 정상 인계가 지연된다.

외부 소유자는 해당 수락 결과가 실제 transcript에 저장되고 뒤따른 텍스트 `end_turn`이 확인되며 다른 Desktop 세션도 유휴일 때만 Windows Restart Manager로 정확한 앱 PID·생성 시각·사용자를 확인해 정상 종료한다. 강제 종료·사용자 마우스/키보드 입력은 사용하지 않는다. 원래 Code 프로세스가 끝난 다음 그 세션에 기록된 네이티브 Claude Code 실행 파일을 단 한 번 `--resume --print`로 실행한다. 복구 구간에는 Desktop이 닫혀 있으며, 같은 transcript·프로젝트·기존 Strata 모델 경로·추론 수준·권한 모드로 미완료 작업을 이어간다. CLI/MCP 출력 본문은 복구 로그에 보관하지 않는다. 최대 실행 시간은 도구 인자로 정하는 1..86400초이며 기본은 24시간이다.

복구 요청은 체크포인트와 실제 파일을 확인한 뒤 `acknowledge_desktop_restart`에 전달받은 작업 ID·nonce·원래 native session_id를 전달한다. 확인이 거절되거나 취소 상태면 작업을 계속하지 않는다. 복구 CLI가 끝나면 기존 Desktop 세션 링크를 한 번 열고 새 앱 프로세스와 원래 세션의 포커스 기록을 확인한다. `desktop_restart_status(operation_id)`의 `ready`는 이 인계·복구 거래 완료만 뜻하며 전체 사용자 작업 수락 조건의 충족을 대신하지 않는다. 실제 파일·테스트·최종 보고로 작업 완료를 판단한다.

`cancel_desktop_restart`는 종료 전이면 앱을 건드리지 않고, 종료 후면 소유한 복구 실행만 중지한 뒤 앱을 다시 연다. 원래 MCP가 종료되는 것은 인계를 취소하지 않으며 사용자의 명시적 중지는 별도로 전달한다. 같은 ID의 재조회·재전송은 기존 영수증만 돌려준다. 저장 실패·불확실한 정상 종료·확인 없는 재개·기한 초과는 자동 반복하지 않고 `failed` 또는 `needs_attention`으로 남긴다. 소유자 자체가 중단된 비종결 거래도 자동 재실행하지 않는다.

새 Desktop 세션은 UUID를 실행 인자에 넣지 않을 수 있다. 선택 기능이 켜진 경우 기존 `SessionStart` 훅이 실제 UUID와 네이티브 프로세스의 PID·생성 시각·소유 사용자·Desktop 소유자를 전용 상태 폴더에 묶어 기록한다. 재시작 도구는 이 연결 또는 명시된 `--resume` 인자를 확인하며 최근 대화 목록에서 대상을 추측하지 않는다. 이전 훅을 사용하던 세션은 설정 적용 후 다시 열어야 한다. 복구 중 사용자가 원래 Desktop 대화를 다시 열면 소유한 임시 실행을 중지하고 확인 필요 상태로 남겨 두 개의 작성자가 같은 대화를 변경하지 않게 한다.

3p 프로필은 OS의 대화 복귀 링크를 무시할 수 있다. 설정기는 기존 CUA 연결을 사용하는 백그라운드 복귀도 함께 켠다. 이 경로는 확인된 새 Desktop 창의 접근성 트리에서 저장된 대화 제목과 정확히 일치하는 버튼이 하나일 때만 한 번 선택하고, 해당 UUID의 실제 포커스 변경을 확인한다. 사용자 마우스·키보드 입력, 좌표 추측, 전경 권한 자동 승인이나 클릭 재전송은 사용하지 않는다. CUA가 없거나 제목이 중복되거나 트리가 잘렸으면 `needs_attention`으로 남긴다. 일반 개발 요청에서는 이 복귀용 CUA를 실행하지 않는다.

같은 Windows PC·같은 사용자의 로컬 Desktop과 기존 supervisor를 기준으로 하며 외부 PC의 Desktop 재개까지 검증한 기능은 아니다.

[공식 Desktop 문서](https://code.claude.com/docs/en/desktop)의 `claude --desktop --resume`은 프롬프트를 받지 않으므로 이 구현은 설치된 네이티브 CLI의 별도 `--resume --print`와 기존 Desktop 세션 열기를 구분한다. 현재 자동 복구의 OS 어댑터는 Windows만 구현되어 있으며 macOS/Linux에서 동일 동작을 검증했다고 보고하지 않는다.

## 검증 범위

기본 검증은 설정·실제 health·필요한 파일 작업 한 번과 후속 수정이다. 성능 변경은 같은 요청·모델·캐시 조건에서 비교한다. 실제 Code 화면, 262K 압축, OS/프로그램 재시작·복구, 장시간 무인 실행은 각각 실행 증거가 있을 때만 성공이라고 표시한다. CUA·REA 연결 목록 조회를 GUI 조작이나 실제 역분석 성공으로 확대하지 않는다.

저장소 신뢰, `settings.json`의 도구 허용 규칙, Code 세션의 권한 모드, Desktop에 표시된 도구 승인창은 서로 다른 상태다. 도구 승인창이 보이면 실제 결과가 돌아오기 전까지 해당 호출은 미실행으로 기록한다. 이 승인 대기는 그 도구 검증만 막으므로 독립적인 저장소 작업은 계속한다. 승인창을 없애려고 권한 규칙을 넓히거나 전체 MCP 호출을 자동 허용하지 않는다.

OpenCodex 관측의 `post_first_output_tokens_per_second`는 출력 토큰 수를 첫 콘텐츠 이후의 전체 요청 시간으로 나눈 유효 스트림 속도다. 프록시와 스트림 처리 시간도 포함하므로 GPU 단독 디코딩 속도로 해석하지 않는다. 작은 최근 표본은 원인 탐색용이며 같은 요청·모델·캐시 조건의 반복 측정을 대체하지 않는다.

Claude Desktop에 답변 본문이 보이는데 턴이 계속 실행 중일 때만 OpenCodex 로그를 추가로 읽는다. 기본 `doctor` 경로에 CLI 로그 조회를 넣지 않아 상태 확인 비용을 늘리지 않는다. 필요하면 `ocx logs filter --surface claude --time-window 15m --limit 12 --json`을 한 번 실행한다. `claude` 필터는 Claude CLI와 Desktop을 나누지 않으므로 타임스탬프를 실제 화면 활동과 대조하고, 출처를 구분할 근거가 없으면 요청 귀속을 **미검증**으로 둔다. `all` 필터에는 다른 클라이언트 요청도 섞일 수 있어 Claude 화면 원인 진단에 사용하지 않는다. `timestamp`, `requestedEffort`, `status`, `durationMs`, `firstOutputMs`, `genStartMs`, `lastOutputMs`, `closeReason`, 입력·캐시·출력 토큰 수만 허용 목록으로 살핀다. 요청·대화 ID, 프롬프트, 응답, 헤더는 출력하거나 보고서에 복사하지 않는다. 설치된 OpenCodex 2.92.0에서 `closeReason=terminal`은 upstream body EOF 기록이며 Anthropic `message_stop`이나 Desktop 완료 표시를 증명하지 않는다. 실제 SSE 종료 이벤트가 계측되지 않았다면 이를 **미검증**으로 남기고 원인을 단정하지 않는다. 재현 확인은 파일을 건드리지 않는 격리된 자체 산술 요청만 사용하며, 실제 사용자 작업을 중지하거나 재시작하지 않는다.

화면에 최종 텍스트가 보이는데도 `중지`가 남으면 OpenCodex 응답 종료와 Claude 내장 CLI의 `turn_complete`/큐 종료 시각을 읽기 전용으로 대조한 뒤 화면을 다시 캡처한다. 진단 로그에 공통 세션 ID가 없으면 시간상 일치는 강한 정황으로만 기록하고 요청 귀속을 확정하지 않는다. CLI 완료와 UI 활성 상태가 오래 어긋나면 이를 **Desktop 화면 상태 불일치 의심**으로 남긴다. 계획을 유지했거나 파일·도구·명령 작업을 마친 Desktop Code 턴이면 사용 가능한 `mcp__ccd_turn__wrap_up`을 호출해 현재 결과와 남은 일을 기록하고 화면이 완료 상태로 바뀌는지 확인한다. 최근 격리 세션에서는 READY 뒤에도 실행 표시가 남았고 별도 wrap_up 요청 후 완료 표시로 바뀌었지만, 후속 요청 자체가 화면을 갱신했을 가능성이 있어 누락된 wrap_up이 유일한 원인이라고 확정하지 않는다. 백엔드 요청·CLI 대기열이 실제로 끝나지 않았다면 wrap_up으로 덮지 않는다. 사용자 작업의 유휴가 별도로 확인되지 않는 한 중지 버튼·프로세스 재시작으로 화면을 정리하지 않는다.

### Claude Desktop Code 성능 비교

- 먼저 `environment_status`로 실제 Strata 모델·컨텍스트·MCP와 OpenCodex 최근 지연/캐시 표본을 기록한다. 표본 지연은 원인 분리가 아니므로 Code 화면의 시작·첫 응답·첫 도구·최종 idle 표시와 함께 읽는다.
- 진단 전용 폴더의 고정 파일 작업을 사용하고 요청 문구, 모델, 노력 수준, MCP 상태를 고정한다. 한 비교에서 바꾸는 값은 컨텍스트 크기 또는 노력 수준 하나뿐이다. 각 조건은 새 세션에서 실행하고 캐시가 준비된 실행과 차가운 실행을 구분한다.
- 작업을 모두 조합한 거대한 테스트 표 대신 두 단계로 좁힌다. 먼저 대표 중간 크기 요청으로 Low/Medium/High를 비교하고, 선택한 수준에서 32K·64K·128K·자동 압축 기준 직전 크기를 비교한다. 각 조건은 최소 2회 탐색한 뒤 효과가 보일 때만 3회 짝지은 재측정으로 결론을 낸다.
- 현재 PC의 Qwen Desktop 경로는 Claude Code 내장 ToolSearch로 사용자 MCP 스키마를 지연 로드하고, CUA·REA 하위 도구의 검색·호출은 `agent-tools` 디스패처가 제공한다. 코드 작업에서는 별도 CUA·REA 카탈로그를 미리 올리지 않으며, GUI 조작은 `search_tools(server="cua-driver", ...)`, 바이너리 역분석은 `search_tools(server="rea", ...)`로 필요한 도구만 찾는다. 도구 결과의 정확한 이름·스키마를 확인한 후 `call_tool`로 실행한다. `/mcp`에서 확인할 서버는 일반 프로젝트에서 `agent-tools`, 유지보수 프로젝트에서 추가로 `strata-maintenance`다. 디스패처가 자식 MCP 실행을 관리하므로 CUA·REA를 프로젝트별로 끄고 켤 필요가 없다. 직접 연결 방식은 명시적으로 설정 모드를 바꾼 경우에만 사용한다.
- 현재 on-demand 모드에서 `/mcp`는 `agent-tools` 연결과 유지보수 프로젝트의 `strata-maintenance` 켜기·끄기에 사용하고 CUA·REA 선택은 `search_tools`에 맡긴다. 직접 CUA·REA 등록 모드로 전환한 경우에만 서버별 비활성화가 프로젝트에 기억된다는 점을 고려해 필요한 서버를 다시 켜고, `/context`에서 전환 전후 비용을 확인한다.
- 압축 시험은 현재 설정된 `autoCompactWindow`를 기준으로 압축 직전·직후 컨텍스트 표시와 OpenCodex 입력/캐시 토큰을 기록한다. 압축이 끝난 같은 Code 대화에서 작은 후속 수정·파일 재읽기·독립 확인을 끝내고, 최종 idle 표시까지 확인한다. 현재 설정기는 모델 창과 자동 압축 창을 모두 262,144로 맞춘다. Claude의 압축·응답 버퍼는 이 창 안에 남으므로 입력 262,144토큰과 별도 출력을 동시에 넣을 수 있다는 뜻은 아니다.
- 기준 실행과 후보 실행에서 첫 출력 시간, 전체 응답 시간, 도구 호출 수/중복, 입력·캐시·출력 토큰, 파일 검증 결과, UI의 최종 완료/idle 상태를 함께 기록한다. 완료 문구만 나온 경우나 HTTP 200만 나온 경우는 전체 Code 작업 완료 증거가 아니다.
- 128K 이상 또는 압축 경계 시험은 GPU 부하가 큰 별도 측정이다. 게임이나 다른 GPU 작업이 실행 중이면 실제 추론을 시작하지 않고 읽기 전용 상태·기록만 수집한다. 실행 시점·온도·GPU 메모리·동시 작업 상태를 남기고, 효과가 재현되지 않으면 설정을 되돌린다.

### 매 프롬프트 훅 비용

한국어 응답 정책은 생성된 전역 `CLAUDE.md`와 프로젝트 지침에 이미 저장한다. 같은 정적 안내만 다시 전달하는 관리 `UserPromptSubmit` 훅은 매 프롬프트마다 Python 프로세스를 새로 시작하므로 등록하지 않는다. 현재 설정기의 `setup`은 자신이 관리하던 해당 훅만 제거하며, 사용자 소유 훅은 보존한다. 프로젝트별 지침과 재개·압축 문맥을 보충하는 `SessionStart` 훅은 `startup|resume|clear|compact|fork`에서 유지한다. 프롬프트마다 달라지는 외부 상태가 실제로 필요해지면 먼저 동적 입력과 비용을 측정한 뒤 추가한다.

Desktop의 `/context`에서 `MCP tools` 합계는 제품 내장 Code·브라우저·터미널·예약 작업 도구까지 포함할 수 있다. 일반 프로젝트의 on-demand 사용자 MCP는 `agent-tools` 기본 2개와 선택형 웹 검색 도구이며, 유지보수 프로젝트에서만 `strata-maintenance` 9개가 추가된다. 이 두 서버 외부의 도구 수/토큰을 CUA·REA 스키마 비용으로 계산하지 말고, 앱 내장 도구를 사용자 MCP 설정에서 삭제하려고 하지 않는다. 사용자가 관리하는 MCP 중복은 `doctor.mcp_delivery.duplicate_direct_servers`로 확인한다.

사용자가 Claude Desktop Code 세션에서 권한 확인을 생략하도록 명시적으로 요청한 경우에는 MCP 도구별 `allow` 규칙을 넓히지 말고 앱 수준 권한 모드를 사용한다. Claude Desktop 설정의 Claude Code 항목에서 `Allow bypass permissions mode`를 켜고, 요청된 경우 사용자 `settings.json`의 `defaultMode`를 설정한다. 기존 저장값이나 폴더 신뢰만으로 현재 세션 모드를 추정하지 말고 Code 화면의 모드가 `권한 무시`인지 확인한다. `agent-tools.call_tool`을 전역 허용 목록에 추가하지 않는다. 이 모드는 세션에서 명령과 도구의 확인창을 건너뛰므로 사용자의 명시적 선택이 필요하며, 코드·환경을 바꾸지 않은 도구 경로 시험으로 한 번 확인한 사실을 모든 도구·후속 세션의 검증으로 확대하지 않는다.

## 최근 연결 오류 구분

`environment_status.transport.messages_route_observed.failure_summary`는 최근 표본의 실패 건수·고정 분류·마지막 실패의 시각/HTTP 상태/소요 시간을 반환한다. 기록의 `ECONNREFUSED`만 `upstream_connection_refused`로 구분하고 나머지는 `unclassified_http_error`로 둔다. 원문 오류·헤더·자격증명은 반환하지 않는다. 현재 health 준비 상태와 과거 실패 이력을 구분하며, 이 분류만으로 서버 정지 원인이나 재전송 안전성을 확정하지 않는다. 원래 요청·재시작 영수증·현재 활동 상태를 먼저 확인한다. 기존 MCP 프로세스가 이전 모듈을 로드했다면 새 MCP 인스턴스에서 이 필드를 확인한다.


## Messages 본문 전달 검사

현재 ON 프로필은 `anthropic_response_guard: true`로 도구 요청의 일반 본문을 도구 선택이 끝날 때까지 보류하고, 도구와 함께 나온 본문을 제외한다. thinking·도구 인자는 계속 전달하고 도구 없는 최종 보고는 보존한다. 긴 일반 답변의 첫 본문 표시가 늦어질 수 있다. 명시적인 JSON 전용 지시에는 JSON 구간을 검증해 전달하며 값은 임의로 고치지 않는다. 기본 서버·OFF는 비활성이다. 동작·한계·원복·실측은 [CLAUDE_RESPONSE_DELIVERY_20261027_KO.md](CLAUDE_RESPONSE_DELIVERY_20261027_KO.md)를 확인한다. 해제하려면 ON 템플릿과 생성 프로필의 플래그를 false로 바꾸고 기존 재시작 도구를 사용한다.
