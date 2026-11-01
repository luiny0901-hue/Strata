# Claude Desktop Code 실제 경로 확인 — 2026-10-26

## 확인 범위

Claude Desktop **Code 화면 → OpenCodex `127.0.0.1:10100` → Strata `127.0.0.1:8080`** 경로를 현재 PC에서 직접 확인했습니다. 작업 폴더는 `C:\Users\luiny\Strata-opencode-session-recovery`이며, 이 세션에서 해당 폴더 신뢰를 허용했습니다.

## 결과

- Code 화면의 `strata-maintenance.environment_status` 도구 호출이 성공했고, 준비 상태의 6개 검사(`shared_route`, `shared_model`, `context`, `strata_loaded`, `desktop_gateway`, `desktop_default`)가 모두 통과했습니다.
- Code 화면에서 실제 모델은 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, 262,144 토큰으로 확인했습니다. Desktop 프로필의 wire model은 `claude-fable-5-p035`이며, Strata 모델로 연결됩니다.
- OpenCodex는 Claude Messages를 direct/native 방식으로 Strata에 전달하며, 도구·추론·생각 예산·캐시 필드를 통과시킵니다. 최근 경로 기록에서도 Desktop 요청 5/5가 HTTP 200으로 끝났습니다.
- `/mcp` 화면에서 `cua-driver`, `rea`, `strata-maintenance`가 모두 `Connected`로 표시됐습니다. `environment_status` 첫 호출은 Code 화면에서 도구 권한을 요청했고, 이 검증에는 일회 허용을 사용했습니다. 지속 허용이나 자동 승인 설정은 변경하지 않았습니다.
- Claude Code의 `/compact`가 “122.8k개 토큰 절약”을 표시했습니다. 이어 같은 세션에 파일 수정·도구 호출 없는 후속 요청을 보내 연결 및 압축 결과에 관한 응답을 받았습니다. 따라서 이 짧은 GUI 시험에서는 압축 이후 세션 재개가 확인됐습니다.

## 지연과 컨텍스트

| Desktop 요청 관측 | 결과 |
| --- | ---: |
| 최초 대용량 요청 | 127,721 입력 토큰, 캐시 0, 약 43초, 첫 출력 182ms |
| 새로 고친 최근 표본 | 총 12/12 성공: CLI 3건 중앙 3,045ms/첫 출력 18ms, Desktop 9건 중앙 6,512ms/첫 출력 60ms |
| 최신 Desktop 요청 | 134,143 입력 토큰 중 133,632 캐시(99.6%), 5,418ms, 첫 출력 55ms, 출력 409토큰 |

최신 요청은 입력 토큰 대부분을 캐시에서 재사용했습니다. 캐시가 없던 첫 대용량 요청보다 최근 표본이 빨랐습니다. 이는 최근의 작은 표본이며, 같은 입력을 통제해 반복한 벤치마크가 아닙니다. 모든 요청이 이만큼 캐시될 것으로 보장하지 않습니다. 첫 요청은 첫 출력 대기보다 큰 캐시 미스 입력과 함께 지연됐으므로 대규모 cold prefill이 주된 병목이라는 해석이 타당하지만, API 기록은 연산 단계를 직접 분해하지 않습니다.

현재 저장 설정은 최대 컨텍스트 `262144`, 응답 상한 `32000`, 자동 압축 창 `262144`입니다. `settings.json`과 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 값은 일치합니다. 저장 설정만으로 Desktop의 정확한 런타임 압축 임계값을 단정하지 않으며, 화면의 컨텍스트 표시와 서버 한도도 구분합니다. 실제 Code 화면의 압축 시험 결과는 아래 2026-10-26 부하 시험 절에 기록했습니다.

## 변경 및 남은 범위

앞선 짧은 점검에서는 라우팅·모델·MCP·권한·서버 설정을 변경하지 않았습니다. 당시 표본에서 cold 입력 뒤 캐시 재사용을 관찰했지만, 통제된 성능 비교는 아니었습니다. 현재 저장된 context 및 자동 압축 창은 모두 262,144입니다. 실제 Code 화면의 장문 압축과 후속 수정은 아래의 후속 부하 시험에서 확인했습니다.

위 문단은 앞선 짧은 GUI 표본의 범위입니다. 뒤에 추가한 실제 Code 화면 부하 시험은 격리된 코딩 fixture를 수정하고 자동 압축 뒤 후속 수정까지 확인했으며, 저장소 빌드·재부팅 뒤 복구·외부 PC 연결과는 별도 범위입니다. CLI의 기존 측정은 Desktop Code 증거로 대체하지 않습니다.

이번 검증 과정에서 사용 안내의 `run-claude-opencodex.bat` 실행 경로가 현재 저장소에 없고, 기존 `run-claude-strata.bat`는 터미널 CLI 실행기임을 확인했습니다. 공통 안내를 Claude Desktop Code의 실제 화면 절차로 바로잡았습니다.

## 실제 Code IDE에서 실행한 격리 유닛 검증

같은 신뢰된 Code 작업 공간에서 아래의 지정된 명령만 한 번 실행했습니다. Code가 작업 폴더를 확인하기 위해 읽기 전용 경로 명령도 별도로 요청했고, 두 승인 모두 `한 번만 허용`으로 처리했습니다. 지속 허용이나 자동 승인 모드는 켜지 않았습니다.

```powershell
& 'C:\Users\luiny\Strata\.venv\Scripts\python.exe' -m unittest tools.test_claude_maintenance tools.test_claude_opencodex_client -v
```

| 모듈 | 테스트 | 통과 | 실패·재시도 |
| --- | ---: | ---: | ---: |
| `tools.test_claude_maintenance` | 11 | 11 | 0 |
| `tools.test_claude_opencodex_client` | 23 | 23 | 0 |
| 합계 | 34 | 34 | 0 |

Code 화면의 최종 응답에 성공 합계와 격리 실행 범위가 표시됐습니다. 테스트는 임시 fixture를 사용했고 운영 Strata/OpenCodex 서버를 호출하거나 재시작하지 않았으며, 저장소 파일·설정 변경이나 설치도 하지 않았다고 Code가 보고했습니다. 따라서 이 결과는 Claude Desktop Code를 통한 명령 실행 경로와 해당 CPU 단위 계약 테스트의 증거입니다. 운영 서버 재시작, 실제 GUI 조작, 262,144 토큰 장시간 세션은 검증하지 않았습니다.

### 완료 상태 지연 관측

테스트 완료 보고에는 총 13.9초와 34/34 성공이 표시됐지만, Desktop은 결과가 보인 뒤에도 약 8분 후까지 `Claude가 응답 중` 및 테스트 단계 `실행 중`을 표시했습니다. 같은 시점의 로컬 프로세스 목록에서 해당 unittest 명령 프로세스는 찾지 못했습니다. 읽기 전용 경로 기록의 최신 Desktop 요청은 HTTP 200, 5,418ms, 첫 출력 55ms, 출력 409토큰이었습니다. `Stop`을 누른 뒤 Desktop 상태가 `응답 완료`로 바뀌고 이미 생성된 최종 보고서가 확정됐습니다. 이는 한 번 관찰한 UI 완료 상태 불일치이며 원인을 확정하거나 반복 재현한 것은 아닙니다. 서버 경로 설정은 바꾸지 않았습니다.

이후 저장소 루트에 `CLAUDE.md`를 추가해 Claude Code가 `AGENTS.md`를 프로젝트 지침으로 읽고, Strata/OpenCodex/Desktop 실행 환경을 수정하는 경우에만 유지보수 안내를 적용하도록 연결했습니다. 이 파일은 위 테스트 세션 종료 뒤 추가했으므로 해당 세션에서 자동 로드됐다는 검증은 아닙니다. 새 Code 세션에 적용됩니다. `START-HERE-AGENT-KO.md`도 Desktop Code를 주 경로로 안내하고 CLI 실행기와 구분하도록 정리했습니다.

참고: [Claude Code Desktop](https://code.claude.com/docs/en/desktop), [프로젝트 지침과 AGENTS.md](https://code.claude.com/docs/en/memory), [Desktop 권한 모드](https://code.claude.com/docs/en/desktop#choose-a-permission-mode), [모델 및 컨텍스트 설정](https://code.claude.com/docs/en/model-config), [Claude Code 기능과 컨텍스트 비용](https://code.claude.com/docs/en/features-overview).

## 후속 점검: MCP 도구 검색 경로와 컨텍스트 비용

신뢰 승인 후 현재 Code 세션에서 `/context`를 다시 확인했습니다. MCP 도구가 318개이고 도구 설명·스키마가 98.5k 토큰(세션 한도의 50.1%)을 차지했습니다. REA `list_cutter_sessions`를 일회 허용으로 한 번 호출해 성공했지만, 해당 호출은 도구 검색이 아닌 직접 MCP 호출이었습니다. 이 결과는 CUA/REA 실행 자체의 성능 증거나 검색 지연 로딩 성공 증거가 아닙니다.

추가 읽기 전용 UI 관측에서 `/context`의 도구별 표시 토큰을 합산했습니다. 총 318개, 98,466 토큰으로 화면의 98.5k와 일치했습니다. REA는 207개 도구·54,717 토큰(전체 MCP 도구 토큰의 55.6%), CUA Driver는 18개·9,975 토큰(10.1%), `ccd_*` 도구는 65개·25,293 토큰(25.7%)이었습니다. 나머지 28개 도구가 8,481 토큰(8.6%)을 차지했습니다. 이는 현재 한 세션의 `/context` 표시를 옮긴 관측치로, 요청 처리 지연이나 토큰 생성 비용을 직접 측정한 값은 아닙니다.

이 경로에서 Claude Desktop Code는 MCP 서버를 `~/.claude.json`에서 직접 실행하고, 모델 요청만 OpenCodex 10100을 거쳐 Strata 8080으로 전달합니다. OpenCodex 2.92.0의 native Messages 본문 허용 목록에는 `tools`와 `messages`가 있고, 본문을 얕게 복사하므로 중첩된 `defer_loading`과 대화 안의 `tool_reference`를 그대로 전달합니다. 설치된 OpenCodex는 `tool-search-tool-2025-10-19` 베타 헤더를 호환 공급자에 전달하지 않습니다. 이는 OpenCodex·Strata의 전달 계약 확인일 뿐, Claude Code가 현재 Strata Qwen 모델에서 검색 도구를 노출한다는 뜻은 아닙니다.

Strata의 실제 실행 fork `C:\Users\luiny\Strata\forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4\serve\frontend.py`에는 `defer_loading` 도구를 기본 프롬프트에서 제외하고 `tool_reference`로 선택된 도구를 다시 노출하는 변환이 있습니다. 격리 테스트는 이 전달 계약만 검증합니다. 현재 Strata Qwen을 선택한 Claude Desktop Code에서는 `ENABLE_TOOL_SEARCH=auto`와 `true`를 각각 확인했지만 ToolSearch가 노출되지 않았고 MCP 도구 전체가 미리 로드됐습니다. 따라서 이 경로의 변환 테스트와 10% 임계값만으로 현재 세션의 도구 검색·절감이 된다고 볼 수 없습니다. 현재 동작은 아래 후속 실험 기록을 기준으로 합니다.

`doctor`는 이 설정과 OpenCodex의 native Messages 도구 전달 미리보기까지 확인합니다. 설정된 사실만으로 현재 열린 Desktop 세션이 바뀌었다고 보지 않습니다. 실제 절감량·검색 성공·완료 시간 향상은 새 Desktop Code 세션에서 측정하기 전까지 미검증입니다.

추가로 `doctor`는 최신 요청 입력 토큰을 `autoCompactWindow`와 비교해 사용률·남은 토큰·캐시 입력 비율을 반환합니다. 이 값은 최근 요청 한 건의 관측값이며 Claude Desktop의 실시간 context meter, 모델 최대치, 전체 세션 성능으로 해석하지 않습니다. 사용량이 없거나 압축 기준을 읽을 수 없을 때는 비율을 추측하지 않고 `unavailable`을 반환합니다.

OpenCodex 경유 Claude Code 관리 설정에는 `ENABLE_TOOL_SEARCH=auto`가 남아 있습니다. 이는 호환 모델 경로를 위한 설정이며 현재 사용자 지정 Strata Qwen 모델의 검색 지원이나 컨텍스트 절감을 증명하지 않습니다. `tools/claude_opencodex_client.py setup`은 3개 관리 파일을 변경하고 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T163025824663Z`에 사본/영수증을 남겼습니다. 이어서 `doctor`가 ready=true, 연결·모델·컨텍스트·native Messages 도구 전달·Desktop gateway 항목을 모두 통과했습니다. 현재 진행 중인 Desktop 프로세스는 재시작하거나 중단하지 않았으므로 이 설정은 새 Claude Code 세션부터 적용됩니다.

검증: `tools.test_claude_opencodex_client` 26개 통과. 실제 실행 중인 Strata fork의 `serve.test_anthropic_tool_cache` 15개 통과, 별도 projection 확인도 통과해 선택된 지연 도구와 eager 도구만 유지되고 미선택 지연 도구는 빠지는 것을 확인했습니다. 첫 fork 테스트 명령에는 fork에 존재하지 않는 `test_anthropic_deferred_tools` 모듈이 포함되어 import 오류가 났습니다. 해당 모듈은 작업 저장소에만 있어, fork에 실제 존재하는 15개 테스트와 동일한 deferred projection 직접 확인으로 다시 검증했습니다. `py_compile`도 통과했습니다.

실제 새 Desktop Code 세션에서 `/context`를 다시 확인하는 단계는 완료하지 못했습니다. 새 세션 버튼 조작의 결과가 불명확해 상태를 재조회했으며 화면은 바뀌지 않았습니다. 기존 세션의 98.5k 표시는 아직 이전 세션의 값입니다. 따라서 실제 절감 토큰 수와 검색 성공, 완료 시간 향상은 아직 검증하지 않았습니다.

참고: [Claude Code 환경 변수와 게이트웨이 도구 검색](https://code.claude.com/docs/ko/env-vars), [Anthropic 도구 검색 프로토콜](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool).

## 2026-10-26 후속 세션·검색 점검

현재 Claude Desktop Code에서 REA 도구 검색을 요청하되 실제 도구 호출과 파일 접근은 금지하는 프롬프트를 보냈다. 응답은 여러 REA 도구를 넓게 나열했으며 실제 분석 도구 호출이나 파일 변경은 없었다. 요청 직전 `/context`는 85.6k 토큰, MCP 도구 스키마 44k/111개였다. 응답 뒤 총 컨텍스트는 131.2k로 늘고 최근 갱신량은 약 45.7k였다. 도구 검색·스키마 로드·응답 본문을 따로 계측할 수 없어 이 증가 전체를 검색 비용으로 단정하지 않는다. 이 표본은 REA 검색 범위를 파일 형식·작업별로 좁히는 지침을 추가할 근거로만 사용한다.

공유 원본 `examples/claude/STRATA_SESSION_RECOVERY_KO.md`의 `MCP·컨텍스트`에 검색 전에 대상 형식·작업·필요한 결과를 정하고, 전체 REA 카탈로그 대신 구체적 검색어로 필요한 후보만 찾으라는 규칙을 추가했다. 가이드 생성 검사 8개와 OpenCodex 설정·라우팅 검사 26개가 통과했고 `git diff --check`도 통과했다. `tools/claude_opencodex_client.py setup`으로 관리 지침을 현재 사용자 프로필에 반영했고 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T165927430861Z`에 저장됐다. 설정상 `cua-driver`·`rea`·`strata-maintenance` MCP가 유지됐다. 후속 `doctor`는 7/7 항목을 통과했고, 최근 OpenCodex 표본은 Claude Desktop 요청 12/12 성공, 중앙 응답 5,155ms, 첫 출력 중앙값 60ms였다. 이는 작은 최근 표본이며 변경 전후 성능 비교는 아니다.

같은 Desktop 시험에서 텍스트 응답이 끝난 뒤 UI가 계속 응답 중으로 표시됐고 Stop을 누른 뒤 완료 상태로 바뀌었다. 해당 OpenCodex 요청은 HTTP 200, 첫 출력 68ms, 완료 28,242ms였고 이후 Strata 슬롯은 idle이었다. 별도의 간단한 Messages 스트림 시험에서는 `message_start`부터 `message_stop`까지 정상 이벤트가 왔다. 간단한 경로의 SSE 종료가 정상이라는 사실은 Desktop에서 재현된 완료 표시 지연의 원인을 설명하지 못한다. 원인은 미확정이며 설정·프록시·서버 변경으로 고쳤다고 주장하지 않는다.

새 지침은 사용자 프로필에 저장됐지만 이미 열려 있던 Claude Desktop 대화의 지침·컨텍스트를 갱신하지 않는다. 다음 새 Code 대화에서 `/context`와 작업별 도구 검색 결과를 확인하기 전까지 실제 도구 스키마 절감량은 미검증이다.

## 2026-10-26 도구 검색 강제 설정 실험 결과

새 Claude Desktop Code 대화에서 `ENABLE_TOOL_SEARCH=true`를 적용해도 도구 검색 기능이 노출되는지 읽기 전용으로 확인했다. 요청은 REA 검색 후보 1개만 찾고, 반환된 도구를 실행하거나 파일을 읽고 변경하지 말라고 제한했다. 화면 응답은 “도구 검색 기능을 사용할 수 없다”고 했고, MCP 도구 호출·파일 접근·파일 변경은 없었다. 따라서 앞 절에서 설명한 OpenCodex 경로 미리보기와 Strata의 `defer_loading`/`tool_reference` 변환은 검색 기능을 실제로 사용할 수 있다는 증거가 아니다.

이 실험의 OpenCodex 최근 요청은 HTTP 200, 24,788ms, 첫 출력 85ms, 입력 76,808토큰, 캐시 입력 16,384토큰(21.3%), 출력 580토큰이었다. 같은 화면의 `/context`에는 196.6k 자동 압축 창과 MCP 도구 설명·스키마 98.5k(50.1%)가 표시됐다. 이 값들은 요청 입력량과 화면의 도구 카탈로그 표시량이라는 서로 다른 지표다. 단일 비통제 표본이므로 검색 비용, 절감량, 기존 설정 대비 속도 향상을 계산하지 않는다.

관측된 경로 사유에는 `anthropic-beta-dropped`가 포함됐다. 현재 설치된 OpenCodex 호환 공급자 경로는 Anthropic 베타 헤더를 허용하지 않지만, 안전 로그만으로 어떤 구체적인 헤더가 제외됐는지는 확인할 수 없다. 그러므로 해당 코드만으로 도구 검색 실패 원인을 특정하지 않는다.

강제 `true`는 기능 노출을 입증하지 못했고, 자동 압축이나 사용 편의성 개선의 측정 이득도 없었다. 관리 설정을 모델 인식 기본값인 `ENABLE_TOOL_SEARCH=auto`로 복구했다. `doctor`의 검색 관련 항목은 설정과 native Messages 경로 미리보기만 의미하도록 `mcp_tool_search_route_preview`, `route_preview_compatible`로 이름을 분명히 했고, `runtime_status=not_verified`를 추가했다. `doctor ready=true`는 ToolSearch가 현재 모델/UI에서 실제 동작한다는 뜻이 아니다.

검증: `tools.test_claude_opencodex_client` 26개 통과. 도구 검색 런타임은 현재 Claude Desktop Code와 사용자 지정 Strata 모델 조합에서 **사용 불가로 관측됨**이며, 호환 모델·게이트웨이로 바꾸지 않은 상태에서 기능 지원을 주장하지 않는다. 기존 MCP 연결과 모델 라우팅은 이 실험에서 변경하지 않았다.

설정 복구 후 `doctor`는 연결·모델·컨텍스트·Desktop gateway·검색 경로 미리보기 등 7개 설정 검사를 통과했다. 최근 OpenCodex 관측은 Desktop 요청 12/12 성공, 중앙 응답 3,927ms, 첫 출력 중앙값 84ms다. 이 작은 혼합 표본은 설정 변경의 성능 효과를 입증하지 않는다. 실제 사용자 설정 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T172731883059Z`에 생성됐다.

## 2026-10-26 작업공간 신뢰와 MCP 권한 분리 확인

Claude Desktop Code에 저장소 폴더 신뢰를 허용한 뒤에도, 화면 하단 권한 모드는 `수동`이었다. 디스크의 새 세션 기본값은 `bypassPermissions`이고 `mcp__agent-tools__search_tools` 허용 규칙도 저장돼 있지만, 현재 세션에는 별도 승인 카드가 표시됐다. 요청 내용은 REA 서버에서 `decompile executable`을 한 번 검색하는 읽기 전용 `agent-tools.search_tools` 호출이다. 이 카드는 모델 내장 ToolSearch 기능과는 별개다. 카드는 두 차례 화면 확인 사이 계속 대기했고, 검색 결과나 후속 호출은 나타나지 않았다. 이 때문에 폴더 신뢰·저장 기본값만으로 현재 세션의 MCP 호출이 승인됐다고 볼 수 없다.

같은 진단에서 저장된 연결은 `ready`, Claude Desktop 프로필은 `desktop_ready`, Strata 모델 컨텍스트는 262,144였다. Strata 실행 슬롯은 1개이며 조회 시점에는 유휴였다. 화면에는 자동 압축 창 196.6k 중 66.6k 사용(34%)으로 표시됐다. 최근 OpenCodex Desktop 표본 12건은 모두 HTTP 200, 응답 중앙값 4,490.5ms, 첫 출력 중앙값 112.5ms였지만 통제 벤치마크가 아니다. 슬롯 조회는 OpenCodex 대기 요청을 감지하지 않는다.

유휴를 먼저 확인한 뒤 모델 생성 없이 로컬 준비 엔드포인트를 5회 조회했다. OpenCodex `/healthz`와 Strata `/health` 합산 중앙값은 45.69ms(28.04–47.94ms), Strata `/slots` 중앙값은 30.49ms(13.18–31.35ms)였고 매 회차 슬롯은 유휴였다. 이 표본에서 제어 경로 지연은 작았지만 prefill·decode 속도나 OpenCodex 대기열은 측정하지 않았다.

승인 카드 입력은 수행하지 않았다. `computer-use` 지침이 앱 내 보안·개인정보 권한 요청을 조작하지 않도록 금지하기 때문이다. 따라서 해당 MCP 도구 검색의 런타임 성공 여부는 **미검증**으로 유지한다. 이는 저장소 파일 권한이나 Strata/OpenCodex 준비 상태의 실패를 뜻하지 않는다.

## 2026-10-26 OpenCodex 요청 페이싱 상태 진단 추가

설치된 OpenCodex 2.92.0 소스의 읽기 전용 `GET /api/provider-request-pacing?name=strata`는 제공자 페이싱 큐와 페이싱 설정이 추적할 때의 동시 실행 수를 반환한다. 현재 실서비스 응답은 `enabled=false`, `queued=0`, `inFlight` 미보고였다. 따라서 `queued=0`을 전체 요청 유휴로 해석할 수 없으며, 기존 `strata_activity=idle`만으로 OpenCodex 전체 경로의 재시작 안전을 판단할 수 없다는 진단 공백이 확인됐다.

`environment_status`에 `opencodex_request_pacing`을 추가했다. 페이싱이 꺼진 경우 `status=not_tracking`, `in_flight=null`과 측정 범위를 반환하며 이 값을 준비 상태나 유휴 판정에 사용하지 않는다. 페이싱 API 오류·잘못된 응답은 `unknown`으로 닫힌다. 유지보수 지침도 페이싱과 Strata 슬롯이 각각 전체 유휴 증거가 아님을 명시한다. MCP 서버 버전은 `1.2.0`으로 올렸다.

확인 결과:

- Claude 유지보수·OpenCodex 클라이언트·on-demand MCP·Claude 지침 단위 테스트 83개 통과, `py_compile` 및 `git diff --check` 통과.
- 새 maintenance MCP stdio 프로세스로 `initialize`와 `environment_status`를 호출해 버전 `1.2.0`, `ready=true`, 컨텍스트 262,144, `not_tracking` 페이싱 상태, Strata 슬롯 `idle`을 확인했다.
- 같은 MCP 프로세스의 `environment_status` 5회 응답 중앙값 148.94ms(138.03–168.21ms). 모델 생성을 하지 않은 로컬 진단 경로이며 변경 전 비교군은 없어 성능 향상으로 해석하지 않는다.
- 사용자 Desktop/OpenCodex/Strata 프로세스는 재시작하지 않았다. 현재 열린 Code 세션은 기존 MCP 프로세스를 계속 사용하므로 이 코드 변경은 새 Code 세션 또는 MCP 재연결 뒤 적용된다.

## 2026-10-26 유지보수 지침 동기화 및 실행기 확인

저장소 신뢰 승인 이후 사용자 프로필의 생성 지침을 현재 저장소 정본과 대조했다. 전역 `CLAUDE.md`와 Unity·Unreal·데스크톱 지침은 생성기와 일치했지만 `~/.claude/guidance/maintenance.md`만 저장소 정본보다 이전이었다. 기존 소유 영수증의 해시와 설치 파일은 일치하고 수동 편집 흔적이 없어 `setup`의 백업·동시 변경 확인 경로로 재동기화했다.

설치 결과 네 개 관리 파일이 바뀌었다: 유지보수 지침, `settings.json`의 훅 실행 Python 경로, `.claude.json`의 두 MCP 실행 Python 경로, 소유 해시 상태 파일이다. 실행 경로는 설치기를 실행한 `C:\Users\luiny\Strata\.venv\Scripts\python.exe`(Python 3.14.7)로 정렬됐다. 이전 Python 실행 파일도 존재했으며, 모델·컨텍스트 한도·압축 창·권한 모드·허용 규칙·MCP 서버 구성은 바뀌지 않았다. 백업 및 영수증은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T211947446215Z`에 있다. 같은 `setup` 재실행은 `changed=0`을 반환했다.

검증: 당시 `doctor` 스냅샷은 `ready=true`, 모델 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, 서버 컨텍스트 262,144, 자동 압축 창 196,608, Desktop gateway 준비 상태를 보고했다. 이는 이 기록 시점의 이전 저장값이며 현재 저장값 262,144는 아래 262K 부하 시험 절에서 다시 확인했다. 최근 Claude Desktop 요청 표본은 12/12 HTTP 200, 응답 중앙값 4,490.5ms, 첫 출력 중앙값 112.5ms였다. 이는 작은 최근 표본이며 벤치마크나 변경 전후 성능 비교가 아니다. `claude mcp list`에서 `agent-tools`와 `strata-maintenance` 모두 연결됐다. 유지보수·OpenCodex·Claude 지침·on-demand MCP 검사는 106개 통과했고 `git diff --check`도 통과했다. Git은 기존 다수 수정·미추적 상태였으며 이 보고 외에 기존 작업물은 건드리지 않았다.

실행 중인 Claude Desktop 세션은 재시작하지 않았다. 설정은 새 세션에 적용된다. 현재 Desktop 세션의 MCP 승인 카드 처리와 on-demand 도구의 실제 호출 성공은 이 확인으로 검증되지 않았다. 페이싱 상태도 `not_tracking`이므로 진단에서 전체 OpenCodex 유휴를 증명하지 않는다.

## 2026-10-26 호스트 메모리 관측 추가

장문 작업의 메모리 병목을 Claude Code가 점검할 근거가 없어 `environment_status`와 `doctor`에 읽기 전용 `host_memory`를 추가했다. Windows는 `GlobalMemoryStatusEx`, Linux는 `/proc/meminfo`의 `MemAvailable`, 그 밖의 POSIX는 `sysconf`를 사용한다. 별도 패키지나 GPU 호출이 없고, 사용할 수 없는 플랫폼에서는 `unavailable`로 닫힌다. 값은 전체·가용 물리 메모리와 가용 비율뿐이며 GPU 메모리, 프로세스별 점유, 모델별 추가 요구량 또는 실행 가능 판정을 포함하지 않는다. 유지보수 MCP 버전은 `1.2.1`이다.

실제 maintenance MCP 새 프로세스에서 `initialize`와 `environment_status`를 호출해 버전 `1.2.1`, `ready=true`, `host_memory.status=observed`, Strata 슬롯 `idle`을 확인했다. 당시 값은 전체 130,946MiB, 가용 25,801MiB(19.7%)였다. 별도 Windows 5초 표본은 Claude Code 7개 프로세스·2.88GiB, Strata 약 64GiB 작업 집합, 127.9GiB 전체 중 약 25GiB 가용을 보였다. 이 한 번의 표본은 메모리 병목이나 컨텍스트별 안전 용량을 입증하지 않으며 제한 임계값을 바꾸지 않았다.

검증: 첫 Linux/POSIX 모의 검사 묶음 67개에서는 Windows Python에 없는 `os.sysconf`를 검사 설정이 만들지 못해 한 검사가 실패했다. 모의 환경에 POSIX 함수를 명시한 뒤 같은 67개가 통과했고, OpenCodex·Claude 지침·클라이언트·on-demand MCP를 포함한 회귀 묶음 109개도 통과했다. 변경된 Python 모듈·검사 `py_compile`, 실제 MCP 프로토콜 호출, `doctor ready=true`도 통과했다. 생성 지침을 사용자 프로필에 적용했으며 `setup`은 유지보수 안내와 해시 상태 두 파일만 변경했다. 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T212804617732Z`이고 재실행 결과 `changed=0`이었다. Desktop UI의 새 세션에서 `/context`를 확인하지 않았으므로 실제 UI에 값이 표시되는지는 새 세션 적용 후 확인 대상이다.

## 2026-10-26 Claude Desktop Code의 REA 검색 승인 및 실행 확인

앞서 대기 상태로 기록했던 동일한 읽기 전용 요청을 이어서 검증했다. 사용자 승인 뒤 현재 프로젝트의 `agent-tools.search_tools` 권한 카드에서 `항상 허용`을 선택했다. 화면에는 이 선택이 로컬 프로젝트 설정에 저장된다고 표시됐다. 요청은 `server="rea"`, `query="decompile executable"`, `limit=1`이며, Claude Desktop Code가 이를 한 번 실행해 카탈로그 결과 1건(`batch_decompile`)을 보고했다. 파일 접근·변경은 없었고 검색 결과에 나온 도구를 추가 실행하지 않았다.

따라서 Claude Desktop Code에서 REA 도구 카탈로그 검색까지는 실제 UI 경로로 확인됐다. 이는 검색 도구 호출의 증거일 뿐 `batch_decompile` 실행, 실제 파일 분석, 다른 프로젝트나 새 세션의 권한 상속은 검증하지 않았다. 권한은 화면 안내에 따라 로컬 프로젝트 설정 범위로 저장됐다.

## 2026-10-26 MCP 응답 뒤 Desktop 턴 완료 표시 비교

별도 Claude Desktop Code 세션에서 읽기 전용 `strata-maintenance.environment_status`를 한 번 실행했다. 호출 결과는 `ready=true`, `desktop_ready=true`, 서버 컨텍스트 262,144, 호스트 메모리 130,946MiB 중 24,887MiB 가용(19%), Strata 슬롯 `idle`이었다. OpenCodex 페이싱은 `not_tracking`이라 전체 요청 유휴 증거는 아니다. 당시 최근 Desktop 요청 표본은 12/12 성공, 응답 중앙값 4,446.5ms, 첫 출력 83.5ms, 첫 출력 이후 유효 속도 57 tok/s였다. 이 작은 최근 표본은 성능 벤치마크가 아니다. 이 상태 조회 호출 자체를 시작·완료 시각으로 잰 시간은 약 36.5초였지만 승인 대기, 모델 추론·정리, MCP 호출 및 앱 처리를 함께 포함하므로 도구 실행 시간으로 분리하지 않는다. OpenCodex의 최신 모델 요청 기록은 HTTP 200, 4,994ms, 첫 출력 30ms, 출력 493토큰이었다.

두 MCP 포함 요청에서 최종 텍스트가 화면에 나타난 뒤에도 Claude Desktop이 `응답 중`/`실행 중`을 유지했다. REA `search_tools` 결과는 한 건(`batch_decompile`)이었고 30초 넘게 도구가 `사용 중`으로 보였다. 별도 유지보수 조회도 최종 보고가 나타난 뒤 10초 이상 실행 표시가 남았다. 각 요청 결과를 확인한 뒤 해당 턴의 `중지`를 한 번 누르자 Desktop이 즉시 `응답 완료`로 바뀌었다. 비교용 무도구 요청은 `K-OK` 응답과 `응답 완료` 표시가 자동으로 끝났다. 현재 증거는 두 MCP 턴과 한 무도구 대화의 관측이며 원인을 확정하거나 일반 재현성을 증명하지 않는다. 백엔드 요청 성공만으로 Desktop 완료를 판정하지 않는다. 중복 호출은 하지 않았다.

이 새 세션의 `/context`는 66.9k/196.6k(34%), MCP 정의 33.9k 토큰·96개였다. 펼친 도구 목록에서 `agent-tools.call_tool`(147토큰)과 `search_tools`(179토큰)가 보였고 CUA·REA 전체 카탈로그는 등록되어 있지 않았다. 이전 직접 CUA/REA 등록 세션의 318개·98,466토큰 관측과 비교하면 이 세션은 MCP 전체 목록이 96개, MCP 정의 비용이 33.9k다. 두 세션의 단순 관측 비교이므로 동등 조건 성능 측정으로 해석하지 않는다. 이 프로젝트의 `.claude/settings.local.json`에는 읽기 전용 `mcp__agent-tools__search_tools`와 `mcp__strata-maintenance__environment_status`만 허용으로 저장됐고 `mcp__agent-tools__call_tool` 허용은 없다. 이는 당시 프로젝트 로컬 설정 관측이며 CUA/REA 실제 실행 권한을 넓히지 않았다.

## 2026-10-26 유지보수 MCP 읽기 권한 병합

Claude 공통 설정기에서 실제 `strata-maintenance` 연결이 구성된 경우에만 `environment_status`, `opencodex_service_status`, `restart_status`의 정확한 MCP 도구 이름을 공통 허용 목록에 병합한다. 사용자 소유 규칙은 유지하고, 유지보수 서버가 더 이상 구성되지 않으면 설정기가 자신이 추가했던 규칙만 제거한다. `agent-tools.call_tool`, `restart_strata`, `cancel_restart`는 설정기가 허용하지 않는다. 설정 모드를 바꾸거나 실행 승인을 자동화한 것은 아니다.

현재 사용자 프로필에 설정기를 적용했다. `settings.json`, 유지보수 guidance, 상태 파일 세 개가 바뀌었고 원본 백업 영수증은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T215726104843Z\files.json`이다. 저장된 규칙과 `doctor`에서 세 읽기 도구가 허용 목록에 있고, 유지보수 MCP 설정 및 Claude Desktop gateway가 준비됨(`ready=true`, `desktop_ready=true`)을 확인했다. MCP 런타임 권한은 설정 진단만으로 증명할 수 없어 `runtime_status=not_verified`다. 기존 Desktop 세션은 재시작하지 않았으므로 실제 UI 동작은 새 세션에서 확인해야 한다.

검증: OpenCodex 클라이언트 55개, maintenance MCP와 Claude 안내 24개가 통과했다. 수정한 Python 파일 두 개 `py_compile` 통과, `git diff --check` 종료 코드 0이었다. Git이 기존 파일 일부의 LF→CRLF 변환 가능성을 알렸지만 검사 오류는 아니었다.

## 2026-10-26 Strata GPU·요청 활동 진단 추가

기존 `environment_status`는 호스트 RAM과 Strata `/slots`만 보여 GPU별 VRAM·사용률·온도·전력, 모델 컨텍스트·동시성, Strata 내부 대기 요청 수를 Claude 유지보수 응답에서 확인하기 어려웠다. 현재 Strata의 인증된 로컬 `GET /v1/status`를 최대 256 KiB까지 읽고 허용 목록·숫자 범위를 검증해 `strata_runtime`으로 노출하도록 바꿨다. GPU·RAM 값은 순간적인 장치 전체 관측이며 작업별 메모리 요구량이나 실행 가능성을 보장하지 않는다. 기존 Strata 요청 활동 값을 `strata_activity`와 재사용해 중복 HTTP 조회를 줄이고, 상태 API가 없거나 활동값이 유효하지 않은 경우에는 기존 `/slots` 경로로 대체한다. 두 경로 모두 OpenCodex 미전달 요청까지 포함한 전체 유휴 증거는 아니다. 리다이렉트는 따르지 않고 자격 증명·원본 응답·비허용 필드는 반환하지 않는다. 진단 경로의 네트워크 제한은 상태 요청 최대 1초와 필요 시 제한된 `/slots` 대체 조회로 유지했다. 유지보수 MCP 버전은 `1.2.2`다.

검증 결과:

- 로컬 라이브 읽기 전용 조회에서 `loaded=true`, 컨텍스트 262,144, Strata `in_flight=0`을 관측했다. RTX 3090 Ti는 23,540/24,564MiB, 사용률 0%, 30°C였고 RTX 3090은 1,606/24,576MiB, 사용률 8%, 44°C였다. RAM 사용량은 103.7/127.9GiB였다. 한 시점의 측정이며 부하 테스트가 아니다.
- 로컬 HTTP fixture에서 정상·유휴/바쁨·범위 밖 값·응답 초과·리다이렉트·구버전 fallback·자격 증명 및 임의 필드 비노출을 검사했다. 전체 두 모듈 73개 단위 검사가 통과했다. 첫 실행은 새 maintenance 검사 fixture가 존재하지 않는 `home` 속성을 사용해 1개 오류가 났고, fixture 참조를 수정한 뒤 같은 묶음을 다시 실행해 73개 모두 통과했다.
- 수정 Python 모듈 `py_compile`, `git diff --check`도 통과했다. 저장된 `strata-maintenance` MCP는 이 저장소의 `tools/claude_maintenance.py`를 실행하도록 설정되어 있으나 이미 열린 Claude Code 세션의 MCP 프로세스는 이전 코드를 유지할 수 있다. 새 Claude Code 세션 또는 MCP 재연결 후 실제 `environment_status` 반영을 확인해야 한다. 모델 생성·GPU 부하·서버 재시작은 실행하지 않았다.
- 설정기를 기존 OpenCode 원본 `C:\Users\luiny\.config\opencode\opencode.json`으로 실행해 사용자 Claude 프로필에 유지보수 안내를 동기화했다. `doctor`에서 `ready=true`, `desktop_ready=true`, 생성 안내의 GPU/VRAM 경고와 `/slots` 대체 경로를 확인했다. 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T221643241326Z`이며 변경 파일은 생성 안내와 관리 상태 파일 두 개다.
- 같은 설치 경로의 `MaintenanceTools.call('environment_status')` 읽기 전용 실행은 187.1ms였고 `ready=true`, `desktop_ready=true`, 컨텍스트 262,144 및 위 상태 필드를 반환했다. 이 한 번의 진단 시간은 작은 표본이며 추론 응답 성능 비교는 아니다.

## 2026-10-26 OpenCodex 응답·디코드 계측 기준 교정

최근 Claude Messages의 한 요청에서 OpenCodex `durationMs=13,199`, `firstOutputMs=37`, 출력 37토큰이었고 기존 진단의 `outputTokens / (durationMs - firstOutputMs)`는 2.8 tok/s를 계산했다. 같은 로그에는 `genStartMs=12,796`, `lastOutputMs=13,197`이 있어 실제 생성 구간은 401ms였다. OpenCodex `displayMetrics.decodeTokPerSecond`는 이 짧은 창에 대해 `decode_window_too_short`를 반환했다. 이 경우 2.8 tok/s는 디코딩 속도로 사용할 수 없다.

설치된 OpenCodex Messages 네이티브 경로의 `observeFirstChunk`는 응답 본문의 첫 청크에서 `firstOutputMs`를 기록한다. Strata/OpenCodex가 프리필 중 메시지 스트림을 먼저 열 수 있으므로 이 값은 첫 토큰 지연이 아니다. OpenCodex 행은 입력 66,866토큰 중 32,768 캐시 토큰을 보고했고, Strata의 거의 같은 종료 시각 마지막 요청 통계는 실제 프리필 34,098토큰에 12,718.1ms·2,681.1 tok/s, 출력 37토큰 디코드에 415.6ms·89 tok/s를 기록했다. 입력에서 캐시 토큰을 뺀 값과 Strata 프리필 토큰 수가 일치하고 종료 시각도 맞아 동일 요청이라는 근거가 강하지만, Strata 상태값은 마지막 요청 통계라 다른 동시 클라이언트가 있으면 자동 상관관계로 보지 않는다.

`environment_status` 계측을 바로잡았다. `firstOutputMs`는 `first_response_chunk_ms`로만 표시하고, decode 속도는 OpenCodex generation-window 추정만 채택한다. 짧은 창과 예전 first-visible-output 기반 추정은 `unavailable`로 남긴다. 출력 토큰/전체 응답 시간은 `request_output_tokens_per_second`로 따로 표시해 프리필·추론·게이트웨이 시간을 포함한다고 명시한다. `strata_runtime.last_request_timings`에 프리필·디코드 토큰 수, 속도, 시간도 허용 목록으로 추가했다. 설치된 OpenCodex 패키지는 수정하지 않았다. 유지보수 MCP 버전은 `1.2.4`다.

회귀 검사에는 generation-window/legacy 창 구분, 짧은 창·실패 행 처리, 첫 응답 청크 명칭, 타이밍 비밀 필드 제외를 추가했다. OpenCodex 클라이언트·maintenance 두 모듈 단위 검사 73개가 통과했고, 실제 `environment_status` 코드는 185.8ms에 `ready=true`, `desktop_ready=true`를 반환했다. 최근 12개 Claude Desktop 성공 요청 중 generation-window decode 추정이 있는 6건의 중앙값은 106.8 tok/s였다. 최신 요청은 401ms 창이라 OpenCodex decode 추정은 unavailable이고, 상관 시각의 Strata 마지막 요청 기록은 프리필 2,681.1 tok/s, 디코드 89.0 tok/s를 보였다. 이는 통제된 동일 프롬프트 벤치마크가 아니며 가장 최근 요청 하나의 시간 분해 관측이다.

실제 저장 설정의 `strata-maintenance` 실행 파일·인자 그대로 stdio MCP를 한 번 띄워 `initialize`와 `environment_status`를 호출했다. 응답은 MCP 버전 `1.2.4`, `isError=false`, `ready=true`, `desktop_ready=true`, 컨텍스트 262,144와 새 시간 필드를 반환했다. 첫 스모크 검사기는 응답이 `structuredContent`로 올 것이라 가정해 필드를 못 읽었지만, 이 MCP는 표준 text content 안에 JSON을 반환했다. 검사기 파싱을 바로잡아 같은 읽기 전용 경로를 다시 실행해 성공을 확인했다. Claude 프로필의 유지보수 안내와 상태 두 파일은 기존 설정기로 동기화했고, `doctor`는 `ready=true`, `desktop_ready=true`, 안내문에 첫 응답 청크·decode window 정책 포함을 확인했다. 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T222607305027Z`다. 현재 이미 열린 Claude 세션의 MCP 프로세스는 이전 코드를 유지할 수 있으므로 새 세션 또는 MCP 재연결이 필요하다. 실제 추론·GPU 부하는 실행하지 않았다.

## 2026-10-26 Claude Desktop Code 파일 쓰기·명령 실행 경로 확인

현재 신뢰된 저장소의 새 Code 세션에서 기존에 없던 `claude-desktop-autonomy-check-20261026.tmp` 한 파일을 생성하고, `py` 런처로 UTF-8 BOM 없는 `probe=42`와 LF 한 개만 기록됐는지 검증했다. Claude가 처음 선택한 `python` 명령은 WindowsApps 실행 별칭의 잘못된 경로 오류로 실패했지만, `py`로 전환한 재시도는 PASS였다. 이어 로컬에서 파일 바이트를 독립 확인한 뒤 이 임시 파일만 삭제했다. 최종 파일은 남아 있지 않다.

이 시험은 Claude Desktop Code에서 저장소 파일 쓰기와 명령 실행까지 이어지는 경로를 검증했다. `python` 별칭 문제를 해결하려고 Windows 실행 별칭 설정을 바꾸지 않았다. 공유 원본 `examples/claude/STRATA_SESSION_RECOVERY_KO.md`에 프로젝트 가상환경 우선 사용과 Windows의 고장 난 `python` 별칭을 `py`로 전환하는 규칙을 추가하고, 설정기로 현재 사용자 Claude Code 지침에도 동기화했다. 설정기는 관리 파일 3개를 반영했고 백업 영수증은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261025T230106971002Z\files.json`이다. 이번 세션의 도구 검색, CUA 창 목록, 유지보수 상태 조회, 파일·명령 검증 턴은 모두 Desktop에서 자동으로 `응답 완료`가 됐다. 이전의 완료 표시 지연은 이 표본에서 재현되지 않았지만 장시간 작업 전반의 해결 증거는 아니다. 파일·설정 변경, stage, commit, push는 시험 작업에서 수행하지 않았다.

## 2026-10-26 CUA 도구 조회와 턴 완료 표시 후속

사용자가 작업에 필요한 도구 사용을 허용한 뒤, 현재 Claude Desktop Code 세션에서 `agent-tools.search_tools`로 CUA 도구를 확인하고 `agent-tools.call_tool`을 통해 `cua-driver.list_windows`를 한 번 실행했다. 검색 결과에는 `list_apps`, `list_windows`, `get_window_state`, 백그라운드 `click`·`type_text`·`double_click`·`right_click`, `press_key`·`hotkey`, 그리고 승인 후 전경 입력을 위한 `approved_foreground_action`이 나타났다. `press_key`와 `hotkey`는 별도 백그라운드 입력 도구로 반환됐지만, 이번 회차에서는 실제 키 입력을 실행하지 않았다. 앱 실행용 `launch_app`은 별도 호출 도구로 반환되지 않았고 실행 스키마도 확인되지 않았다. `list_apps`의 `launch_path` 설명은 앱 실행 기능을 뜻하지 않는다.

현재 창 목록 17개에서 Calculator/계산기 창은 없었다. 프로젝트 CUA 정책상 프록시에서 앱을 실행하거나 셸로 우회하지 않으며, 안전한 표적 창이 없을 때 GUI 입력 시험을 진행하지 않는다. 따라서 이번 회차에서 실제 클릭·키 입력은 시험하지 않았고 **미검증**이다. 사용자가 권한을 허용했더라도 현재 필요한 창이 없다는 실행 조건까지 바뀌지는 않는다. 실제 GUI 시험은 대상 앱을 사용자가 열어 둔 뒤 그 정확한 창에서 진행해야 한다.

읽기 전용 `doctor`는 `ready=true`, 10/10 준비 검사를 보고했다. 최근 Claude Desktop Messages 표본은 12/12 HTTP 200, 중앙 응답 2,945ms, 첫 본문 청크 38ms였다. 진단에서 관측된 최신 요청은 입력 100,328토큰(캐시 96,838), 출력 835토큰, 총 10,652ms, 첫 청크 39ms였고 generation-window 디코드 추정은 100.1 tok/s였다. 작은 비통제 표본이며 CUA 동작 시간이나 완료 UI까지의 지연 측정은 아니다. 저장된 권한 규칙은 `agent-tools.search_tools` 허용, `agent-tools.call_tool` 비허용을 유지했다. 검색과 창 목록 호출은 현재 화면의 `권한 무시` 모드에서 성공했고, 별도 권한 팝업은 나타나지 않아 지속 허용 규칙을 넓히지 않았다.

`list_windows`의 최종 텍스트가 화면에 표시된 뒤에도 Desktop은 최소 4초간 `실행 중`과 `중지`를 유지했다. 완료 텍스트와 도구 결과가 이미 보이는 상태에서 `중지`를 한 번 누르자 즉시 `Claude가 응답을 완료했습니다`로 바뀌었다. 이는 앞의 MCP 턴 완료 표시 관측을 다시 확인한 사례다. API 요청은 성공했지만 Desktop 표시 지연의 원인을 분리하지 못했으며, 이 조작은 근본 수정이 아니다. 작업 재실행 없이 화면 상태만 마무리했다.

## 2026-10-26 Claude Desktop MCP 표면과 컨텍스트 비용 재확인

같은 저장소에서 새 Claude Desktop Code 세션을 만들고 기존 미커밋 변경을 이어받았다. 세션 생성 시 전달된 변경 파일 수는 97개였다. 현재 세션 설정에서 저장 파일의 `model`은 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, `effortLevel`은 `medium`, 권한 모드는 `bypassPermissions`로 확인됐다. 반면 열린 Code 화면의 세션 표시에는 같은 Strata 모델과 `높음` 추론 성능이 보였다. 저장된 기본값과 화면의 현재 세션 선택이 일치하지 않으므로, 이 상태만으로 저장 기본값이 실제 세션 추론 설정을 덮어쓴다고 결론 내리지 않는다.

화면의 Context 패널은 MCP 도구 96개와 도구 정의 약 33.9k 토큰(17.2%)을 표시했다. 패널에 표시된 전체 컨텍스트는 71.6k/196.6k였으며, 그 하위 범주의 반올림 합계도 대략 이 값과 맞는다. 반면 같은 새 세션의 `get_usage` 도구 응답은 사용량 113,524토큰과 MCP 도구 60,201토큰을 보고했다. 이후 읽기 전용 `doctor`가 관측한 최신 Strata 요청 입력은 71,587토큰으로, 화면의 71.6k와 반올림 수준에서 일치했다. 따라서 화면 값은 실제 최신 요청 입력과 일치하는 관측치지만, `get_usage`가 반환한 범주별 값은 다른 계측 기준으로 보이며 현재 해석을 확인하지 못했다. 두 도구 비용 수치를 서로 바꾸어 쓰거나 60,201토큰을 실제 요청 입력의 MCP 비용이라고 단정하지 않는다.

저장된 `.claude.json`의 사용자 관리 MCP 두 서버(`agent-tools`, `strata-maintenance`)는 실제 JSON-RPC `tools/list`에서 각각 2개와 5개, 총 7개 도구를 제공했다. Desktop Context 패널의 96개에는 이 7개 외에도 앱 통합 도구가 포함된다. 현재 보이는 목록에서는 CUA/REA를 필요 시 검색하는 `agent-tools` 구조와 유지보수 MCP를 확인했으며, 다른 앱 제공 도구를 사용량 증거 없이 제거하거나 비활성화하지 않았다. 96개 전체 중 사용 빈도·중복·초기화 비용을 독립적으로 모두 검증하지 않았으므로, 더 줄일 수 있는 도구 수는 **미확인**이다.

읽기 전용 설정 점검에서 사용자 저장 파일은 `effortLevel=medium`을 지정하지만, 열린 세션은 `높음`을 표시했다. 현재 세션 UI가 살아 있는 동안 설정 파일 변경이나 세션 재시작은 하지 않았다. 이 관측은 설정 우선순위를 설명하지 못하며, 새 세션 생성 후 실제 적용값을 한 번 더 확인해야 한다. 현재 `doctor`의 이전 관측은 `ready=true`, `desktop_ready=true`, 준비 검사 10/10이었고, 최신 Claude Desktop 요청 표본은 HTTP 200, 총 4,486ms, 첫 본문 청크 36ms, 입력 71,587토큰(캐시 71,191), 출력 394토큰, 추정 decode 106.5 tok/s였다. 표본 하나와 비통제 요청이므로 종단 간 성능 개선 증거가 아니다.

같은 `doctor` 실행은 10/10 준비 검사를 통과하고 `ready=true`, `desktop_ready=true`를 반환했다. 최근 Claude Desktop Messages 요청은 12/12 HTTP 200, 중앙 요청 3,546ms, 중앙 첫 본문 청크 40ms, generation-window 추정 중앙값 104.8 tok/s(유효 표본 9건)였다. 최신 요청은 4,486ms, 첫 본문 청크 36ms, 입력 71,587토큰 중 캐시 입력 71,191(99.4%), 출력 394토큰, 추정 decode 106.5 tok/s였다. 짧고 통제하지 않은 최근 표본이며 벤치마크는 아니다. `opencodex_request_pacing`은 `not_tracking`, MCP 런타임과 ToolSearch도 `not_verified`이므로 전체 동시 요청 대기나 실제 deferred-tool 절감은 이 결과로 판단할 수 없다. 시스템 사용 가능 메모리는 약 23.3GiB(17.8%)였지만 페이지 파일 압박·프로세스 메모리·추론 지연과의 상관은 측정하지 않아 메모리 병목으로 분류하지 않는다.

MCP Context의 앱 UI와 `get_usage` 범주값 차이, 추론 성능의 저장 기본값/현재 세션 차이는 추가 관찰 지점으로 남겼다. 이번 점검은 관측값을 기록했을 뿐 MCP 제공 도구, 지속 권한, 추론 설정, 서비스 구성을 변경하지 않았다.

## 2026-10-26 저장 추론 기본값 진단 보강

유지보수 MCP가 반환하는 `environment_status`는 OpenCodex `doctor` 진단을 그대로 포함하지만, 기존 보고에는 저장된 `effortLevel` 항목이 없어 설정 파일과 Desktop Code 화면의 차이를 진단에서 확인할 수 없었다. `tools/claude_opencodex_client.py`의 읽기 전용 보고에 `effort_level`을 추가했다. 유효한 저장 기본값은 `configured`, 누락은 `missing`, 지원하지 않는 값은 `invalid`로 표시하고, 런타임은 항상 `not_verified`로 남긴다. 이 항목은 연결 준비 `ready`를 바꾸지 않으며 현재 세션이나 개별 요청의 추론값을 가장하지 않는다. 사용자 설정은 변경하지 않았다.

`tools.test_claude_opencodex_client` 60개와 `tools.test_claude_maintenance` 15개, 총 75개 검사가 통과했다. 새 검사는 저장 `medium`·`high`, 값 누락, 잘못된 값, readiness 불변, 유지보수 MCP의 `environment_status` 전달을 확인했다. 네 Python 파일의 `py_compile`도 통과했다. `PYTHONUTF8=1`로 실행한 실제 `doctor`는 종료 코드 0, `ready=true`, `desktop_ready=true`, 저장 기본값 `medium`, 런타임 `not_verified`, 최근 Desktop 요청 12/12 성공을 반환했다. 열린 화면의 `높음` 표시는 별도 세션 상태로 남아 있으므로 우선순위를 확인하거나 변경하지 않았다.

추가로 `~/.claude.json`의 저장된 `strata-maintenance` 실행 명령을 그대로 시작해 JSON-RPC `initialize`와 `environment_status`를 호출했다. 응답은 `ready=true`, `desktop_ready=true`, 새 `effort_level.saved_default=medium`, `runtime_status=not_verified`를 포함했다. `strata_activity=idle`은 해당 시점 Strata 슬롯 관측일 뿐 전체 OpenCodex 대기열의 유휴 증거가 아니다. 실행 중인 Desktop의 MCP 프로세스는 재시작하지 않았으므로, 이미 열린 세션이 이 변경을 로드했다는 주장은 하지 않는다. 새 MCP 프로세스/세션에서 필드를 사용할 수 있다는 실제 저장 실행 경로 확인이다.

Desktop 추론 메뉴도 읽기 전용으로 열어 확인했다. 현재는 `낮음`, `중간`, `높음 기본`, `매우 높음`, `최대`의 고정 선택지가 있으며 이름이 `Auto`인 작업별 자동 선택은 없다. `높음 기본`은 기본으로 표시되는 고정 effort 선택이며 매 요청의 난이도를 보고 선택값 자체를 바꾼다는 의미는 확인되지 않았다. 메뉴를 열고 닫는 동안 기존 `높음`을 유지했다. `the removed client-specific automatic-effort plug-in`의 자동 라우팅은 OpenCode 요청 경로에 속하므로 Desktop Code에 그대로 적용되지 않는다. 현재 UI가 보내는 수동 선택을 자동 경로에서 안전하게 구분할 수 있는지와 Claude Desktop 요청의 작업별 자동 effort 지원은 아직 **미검증**이다. 현재 증거만으로 UI 기본값을 바꾸거나 요청의 수동 effort를 덮어쓰지 않았다.

## 2026-10-26 High·Medium 짧은 요청 비교와 완료 표시 재확인

현재 Claude Desktop Code 화면에서 같은 읽기 전용 산술 요청(`17+25`, 파일·설정 접근 금지)을 High와 Medium으로 각각 한 번 보냈다. OpenCodex 2.92.0의 요청 기록은 각각 `requestedEffort=high`와 `requestedEffort=medium`, HTTP 200을 남겼다. 이는 해당 effort 라벨을 OpenCodex가 관측했다는 증거이며 실제 내부 thinking budget이나 모델 추론량의 증거는 아니다. High 응답은 `사십이`로 보였고 기록은 1,865ms, 첫 본문 청크 34ms, 입력 72,147토큰(캐시 71,582), 출력 22토큰이었다. Medium 응답도 `사십이`였고 기록은 1,393ms, 첫 본문 청크 364ms, 입력 72,362토큰(캐시 72,171), 출력 30토큰이었다. 생성 창은 각각 197ms와 309ms로 짧아 두 요청 모두 유효한 generation-window 디코드 속도가 없었다. 전체 응답 처리율 11.8/21.5 tok/s는 요청 전체 시간으로 나눈 값이므로 디코드 성능 비교에 쓰지 않는다.

두 요청 모두 텍스트가 나타난 뒤에도 Desktop에 `실행 중`/`중지`가 남았다. High는 20초 이상 기다린 뒤 해당 표본의 `중지`를 눌렀고, Medium도 응답 텍스트가 보인 뒤 같은 버튼을 눌러 UI를 정리했다. 두 번 모두 Strata/OpenCodex 기록은 그 전에 HTTP 200으로 끝나 있어, 현재 UI에서 서버 완료와 Desktop의 턴 완료 표시가 다시 어긋난 사례다. 이전 무도구 `K-OK` 대화에서는 자동 완료된 기록도 있으므로 이 결과만으로 모든 요청에서 재현된다고 단정하지 않는다. 단순 SSE fixture에서 `message_stop`을 받았던 테스트도 실제 Desktop 응답의 종료 처리를 입증하지 않는다.

High와 Medium 표본은 각 1건이고, Medium 요청은 첫 표본과 대화 이력이 다른 상태에서 수행됐다. 첫 청크 지연도 서로 달랐으며 디코드 표본이 없어 어느 추론 수준이 빠르거나 품질이 낫다고 결론내릴 수 없다. OpenCodex의 `requestedEffort` 관측은 UI 선택 라벨이 요청 경로에 전달된 점만 확인하며, 모델이 effort 차이를 실제 추론에 어떻게 반영했는지는 **미검증**이다. 화면의 선택 수준은 비교 뒤 기존 `높음`으로 복원했다. 저장된 기본값 `medium`은 변경하지 않았다.

이번 재확인에서 원인을 특정하거나 설정·프록시·서버를 변경하지 않았다. 실행 중인 10100 포트 소유자는 설치된 OpenCodex `2.92.0` 패키지였다. 선택된 native Messages 경로는 upstream SSE 본문을 릴레이한다. 다만 설치된 `messages-shared.ts`의 `tapAnthropicSseForLog`는 upstream body가 EOF에 도달하면 `message_stop`을 확인하지 않고도 `closeReason=terminal`로 기록한다. `message_stop` 수신 여부는 요청 로그에 보존되지 않는다. 따라서 이 로그 값은 스트림 본문 EOF/릴레이 종료만 확인하며 Anthropic 종료 이벤트나 Desktop 턴 완료를 입증하지 않는다. 실제 Desktop 응답에서 종료 이벤트를 관찰한 증거가 없어 완료 표시 지연 원인은 미확정이다. 실제 이벤트 수준 증거와 Desktop UI 상태를 상관시킨 뒤에만 수정 지점을 판단할 수 있다. 해당 UI 상태를 마무리하려고 `중지`를 누른 것은 두 격리 산술 표본에만 적용했으며 사용자 작업은 취소하지 않았다.

## 2026-10-26 단문 완료 표시 지연 재측정

RTX 3090 Ti 단독 AI 기준을 확인하면서 같은 Desktop Code 세션에서 도구를 쓰지 않는 짧은 응답을 두 번 관찰했다. 화면의 컨텍스트 창은 `262.1k`, 요청 입력은 각각 `128,302`와 `128,465`토큰(약 49%)이었다. 이는 압축 경계 부하 시험이 아니다. 실행 중인 `strata.exe` PID `49616`은 GPU index `1`에서만 보였고, `on/off` Strata 프로필은 모두 `gpu=1`, `gpus_asked=true`였다. GPU index `0`의 NVIDIA 프로세스 목록에는 Claude, ChatGPT 및 데스크톱 앱이 있었고 Strata 프로세스는 없었다. index `0`의 38–40% 그래픽 사용률은 AI 추론 사용량으로 계산하지 않는다.

| 시험 | 입력 방식 | OpenCodex 관측 | Desktop 화면 관측 |
| --- | --- | --- | --- |
| A | 접근성 편집 값 입력 | HTTP 200, 1,256ms, 첫 본문 청크 44ms, 입력 128,302, 출력 14 | `완료`가 보인 시점에도 `응답 중`이 유지됐다. 276초 뒤에도 그 상태였고, 격리 시험의 `중지`를 누른 직후 `응답 완료`로 바뀌었다. |
| B | 텍스트 입력 후 Enter | HTTP 200, 951ms, 첫 본문 출력 46ms, 생성 시작 839ms, 마지막 본문 출력 948ms, 입력 128,465(캐시 128,317), 출력 16, `closeReason=terminal` | `B-완료`는 약 103초 시점에 화면에서 확인됐고, 145초에도 `응답 중`이었다. 158초에 격리 시험의 `중지`를 누른 직후 `응답 완료`로 바뀌었다. |

B 로그는 기록된 OpenCodex Bun/CLI 소유자를 사용해 허용된 필드만 읽었다. 설치본 소스에서 `tapAnthropicSseForLog`를 확인한 결과, 정상 body EOF 경로는 `message_stop` 관측 여부와 무관하게 HTTP 200 및 `closeReason=terminal`로 마감한다. 내부 `terminalSeen` 값은 stall/read-error 분기에서만 사용되고 요청 로그에 저장되지 않는다. generation-window 기록도 첫 콘텐츠 시작/델타 시각만 저장하며 terminal event 자체는 보존하지 않는다. 따라서 B 로그의 `closeReason=terminal`은 `message_stop` 증거가 아니고 실제 Desktop 완료 신호도 기록되지 않는다. A는 읽기 전용 `doctor`의 최근 요청 관측값이다. 두 응답 모두 짧은 무도구 시험이라 전체 코딩 작업 성능이나 디코드 속도를 나타내지 않는다. 일반 텍스트 입력 경로에서도 표시 지연이 재현됐으므로 A의 접근성 입력만으로 현상을 설명할 수 없다. 다만 종료 이벤트 수준을 확인하지 못했으므로 문제 위치가 OpenCodex 릴레이인지 Claude Desktop 상태 관리인지 확정할 수 없다. 이에 따라 timeout, 프로토콜, GPU 설정은 바꾸지 않았다.

권한 모드는 대화별로 확인했다. High·Medium 표본을 실행한 원래 대화는 `권한 무시`, REA 검색 완료 기록을 확인한 별도 대화는 `수동`이었다. 어느 대화의 권한 모드도 이번 점검에서 변경하지 않았다.

## 2026-10-26 요청 로그 진단을 선택형으로 분리

`environment_status`에 `include_opencodex_requests`와 `request_window`(15m/1h)를 추가했다. 기본 상태 확인은 로그 CLI 프로세스를 추가 실행하지 않고, 요청 분석을 명시적으로 선택한 경우에만 기록된 Bun/CLI 소유자로 조회한다. 로그 조회는 최대 8초, stdout은 128 KiB에서 스트리밍을 중단하며 최근 최대 12건의 허용된 지연·HTTP 상태·요청 effort·토큰 사용량만 돌려준다. request/conversation ID, cursor, prompt/response, protocol trace, stderr는 결과에서 제외한다. CLI와 Desktop 표면은 묶여 있으므로 UI 시간과의 대조가 필요하고 `close_reason=terminal`은 body EOF일 뿐 `message_stop`이나 앱 완료를 입증하지 않는다. maintenance MCP 버전은 `1.2.5`다.

유지보수 MCP와 OpenCodex 설정 클라이언트 검사 82개 및 두 Python 파일의 `py_compile`이 통과했다. 첫 검증에서 알 수 없는 `terminalStatus` 값이 `other`로 정규화되어도 필드 자체는 남는다는 테스트 실패를 확인했다. 문서의 최소 반환 정책에 맞춰 해당 필드를 아예 제외하고 다시 검사해 통과했다. 128 KiB를 넘는 fixture에서는 조회 프로세스를 중지하고 요청 표본 없이 제한 초과 상태만 반환하는 것도 확인했다. 이 검증은 CPU fixture와 새 MCP 소스의 동작이며, 이미 열린 Desktop 세션의 MCP가 새 버전을 다시 읽었거나 실제 앱 완료 표시가 바뀌었다는 증거는 아니다. 기존 서비스를 재시작하지 않았다.

## 2026-10-26 Claude Desktop Code 262K 압축·후속 수정 부하 시험

RTX 3090 Ti 한 장만 AI 추론 대상으로 사용했다. `nvidia-smi`에서 Strata PID `49616`은 GPU index `1`(RTX 3090 Ti)에 있었고, 이 카드의 메모리 사용량은 약 23,286 MiB였다. GPU index `0`은 RTX 3090으로 약 1.2–1.3 GiB와 25–40% 그래픽 사용률이 보였지만 Strata 프로세스나 추론 대상으로 쓰지 않았다.

Claude Desktop Code의 동일 세션에서 격리된 12개 context fixture 파일을 순서대로 각각 한 번 읽고 코딩 fixture를 구현했다. 시작 화면은 128.5k/262.1k였고 읽기 진행 중 233.5k/262.1k(89%)에 도달했다. 화면에 자동 압축 표시 `압축된 세션 · 224.6k개 토큰 절약`이 나타난 뒤 사용량은 113.9k/262.1k(43%)로 내려갔다. 이는 해당 라이브 Code 세션에서 자동 압축과 같은 턴의 연속 실행을 확인한 증거이며, 모든 세션의 고정 임계값이나 262,144 토큰까지 채운 증거는 아니다.

fixture에서 `EARLY=E17`, `MIDDLE=M29`, `LATE=L43`, `RETRY_LIMIT=3`, `DISCOUNT_BPS=825`, `SHIPPING_FEE_CENTS=599`, `FREE_SHIPPING_THRESHOLD_CENTS=10000`을 추출했다. 구현 뒤 단위 테스트 4개와 보호 검증 `DESKTOP_FIXTURE_PASS`가 통과했다. 이어 같은 압축 후 세션에서 배송비를 699, 무료 배송 기준을 11000으로 수정했고, 압축 전 값 다섯 개와 구현을 유지했다. 후속 단위 테스트 4개와 `DESKTOP_FOLLOWUP_PASS`가 통과했다. 격리 manifest의 context 및 검증 파일 해시 14개도 모두 일치했다.

`doctor`의 후속 최신 모델 요청은 HTTP 200, 입력 132,149토큰(캐시 132,058), 출력 528토큰, 전체 요청 4,891ms, 첫 본문 청크 38ms였다. generation-window decode 추정은 121.5 tok/s(4,345ms 창)였다. 이는 마지막 모델 왕복 한 건이며 파일 열람·도구 실행·압축·후속 변경을 포함한 전체 작업시간이나 262K 일반 프로젝트 성능으로 해석하지 않는다.

완료 표시 지연은 다시 관찰됐다. 첫 fixture의 답변과 검증 결과가 화면에 모두 나타나고 OpenCodex가 HTTP 200으로 종료된 뒤에도 Desktop은 1분 이상 `응답 중`을 표시했고 GPU 사용률은 0%였다. `Ctrl+Enter`로 같은 대화의 후속 수정을 대기열에 넣은 직후 첫 턴이 `응답 완료`로 바뀌었다. 후속 답변도 전부 표시된 뒤 `doctor`는 HTTP 200, GPU는 0%였지만 마지막 화면 관측에서도 `Claude가 응답 중입니다`가 남아 있었다. 별도로 같은 로컬 Messages 경로에 세 가지 읽기 전용 SSE probe를 보냈다. 무도구 요청은 1,407ms, 강제 tool-use 요청은 `stop_reason=tool_use`로 1,220ms, tool-result 뒤 응답은 `stop_reason=end_turn`으로 1,060ms에 각각 HTTP 200으로 끝났으며, 모두 `message_stop`과 본문 EOF를 보냈다. 이 probe들은 로컬 일반·도구 경로가 종료 이벤트를 전달할 수 있음을 보일 뿐, Desktop의 실제 긴 요청에서 받은 SSE 이벤트를 캡처한 것은 아니다. 현재 인증된 Strata 상태는 `context_tokens=262144`, `activity.is_idle=true`, `in_flight=0`, GPU index 1을 `model`, index 0을 `unused`로 보고했다. Claude 자식 프로세스도 없었다. OpenCodex 페이싱은 `not_tracking`이고 Claude–OpenCodex TCP keep-alive 연결은 남아 있었으므로 전체 경로 유휴를 단정하지 않는다. 실사용 Code 경로의 완료 표시 지연은 재현됐지만 정확한 원인 위치는 미확정이다. 진단 로그는 Desktop 요청별 `message_stop`을 저장하지 않으며 설치된 OpenCodex 패키지도 수정하지 않았다. 설정·timeout·서버 재시작은 변경하지 않았다.

## 2026-10-26 매 프롬프트 훅 지연 제거

저장된 `~/.claude/settings.json`에는 매 요청마다 실행되는 관리 `UserPromptSubmit` 훅이 있었다. 이 훅은 한국어 안내만 출력했고, 같은 정책은 이미 생성된 전역 `~/.claude/CLAUDE.md`에 있으므로 매번 별도 Python을 시작하는 비용을 없앴다. 관리 `SessionStart` 훅은 프로젝트 지침 및 압축 후 재개 문맥을 위해 유지했다. 설정기 변경은 자신이 관리하던 프롬프트 훅만 제거하며 사용자 소유의 다른 훅을 보존한다.

설정에 지정된 Python과 훅 명령을 그대로 7회 실행했다. 모두 종료 코드 0이었고, 실행 시간은 254.7–330.8ms, 중앙값은 281.5ms였다. 이는 제거 전 명령의 프로세스 시작 비용 표본이지, 전체 대화 응답시간이 그만큼 줄었다는 실측은 아니다.

`tools.test_claude_opencodex_client`와 `tools.test_claude_code_guidance`는 총 78개 통과했다. 검사는 관리 훅 제거, 사용자 훅 보존, `SessionStart` 유지 사례를 포함했다. 현재 사용자 프로필에 설정기를 적용했고, 백업은 `C:\Users\luiny\.claude\backups\strata-opencodex-20261026T060749202934Z`에 저장됐다. `settings.json`에서는 관리 `UserPromptSubmit` 훅만 의미상 변경됐다. `.claude.json`은 직렬화 형식이 다시 저장됐지만 JSON 값 비교에서 의미상 설정 차이는 없었다. `doctor`는 `ready=true`, `desktop_ready=true`, 모델 컨텍스트와 자동 압축 창 262144, MCP `on_demand_cua_rea`를 확인했다.

후속 읽기 전용 `doctor` 표본은 최근 Claude Desktop 요청 12/12건 HTTP 200, 전체 요청 시간 중앙값 2,555ms, 첫 응답 본문 청크 중앙값 39ms를 보였다. generation-window 디코드 표본은 9건 중앙값 112.7 tok/s였다. 최신 한 건은 1,823ms였고 입력 132,841토큰 중 132,676토큰이 캐시, 출력 61토큰이었다. 짧은 출력 창이라 개별 요청 디코드 속도는 계산되지 않았다. 이 표본은 API 경로의 응답성을 보여줄 뿐이고, 같은 시점 Desktop 턴의 완료/idle 표시나 전체 요청 페이싱을 확인하지 않는다. `opencodex_request_pacing`은 `not_tracking`이므로 요청 경로 전체가 유휴 상태라고 결론내리지 않는다.

## 2026-10-26 CLI 완료와 Desktop 화면 상태 재대조

읽기 전용 화면 캡처를 `2026-10-26 06:25:17 UTC` 직후에 확인했다. 화면에는 `중지`와 실행 상태가 계속 남아 있었고, 컨텍스트는 `132.1k/262.1k`였다. `READY` 문자열도 화면에 보였지만 접근성 트리는 그것을 최신 요청과 확실히 연결하지 못했다. 이전의 15초 대기 뒤에도 실행 상태는 같았다. 화면에서 중지 입력·세션 이동·재시작은 하지 않았다.

현재 OpenCodex `usage.jsonl`에서 마지막 Claude Messages 표본은 `2026-10-26 05:54:30.879 UTC` 시작, HTTP 200, 1,823ms였으므로 기록된 body 완료 시각은 `05:54:32.702 UTC`다. Claude 내장 CLI 진단 로그의 마지막 사용자 입력은 `05:54:30.270 UTC`에 큐에 들어가고 8ms 뒤 시작됐다. `cli_ask_turn_complete`는 `05:54:32.730 UTC`, `cli_drain_queue_complete`는 `05:54:32.731 UTC`이며 큐 종료 시 깊이는 0이었다. OpenCodex body 종료와 CLI turn 종료는 28ms 차이로 맞물린다. 약 30분 뒤에도 화면에 `중지`가 남은 점은 Desktop 표시 상태 불일치 가능성을 높인다.

단, OpenCodex 행과 CLI 이벤트에는 공통 세션 ID가 없어 이것이 같은 Desktop 요청이라는 연결은 시간상 정황이며 확정 상관관계가 아니다. 또한 OpenCodex 로그의 `closeReason=terminal`은 실제 `message_stop` 이벤트를 기록하지 않는다. 따라서 현 증거로 모델 생성이 계속된다고 보기는 어렵지만, Desktop UI 계층의 정확한 원인과 SSE `message_stop` 전달 여부는 여전히 미확정이다. 설치된 OpenCodex 패키지를 수정하거나 세션을 중지·재시작하지 않았다.

같은 Desktop `/context` 화면은 `MCP tools` 96개/33.9k 토큰, `System tools` 17.2k, `Autocompact buffer` 33k, `Free space` 97k를 표시했다. 노출 목록에서 사용자 관리 서버는 `agent-tools` 2개와 `strata-maintenance` 5개였고, CUA·REA 직접 서버는 보이지 않았다. 따라서 on-demand 설정과 직접 CUA·REA 중복 제거는 적용되어 있으며, 나머지 큰 도구 카탈로그는 Claude Desktop 내장 `ccd_*`, Claude Browser, scheduled-tasks, terminal 기능에서 온다. 이 앱 제공 스키마는 사용자 MCP 설정에서 안전하게 줄일 수 있는 항목으로 확인되지 않아 제거하지 않았다. 이 표본에서 `MCP tools` 비용 전체를 CUA·REA 비용으로 간주하지 않는다.

## 2026-10-26 OpenCodex–Claude Desktop–Strata 경로 재점검

`2026-10-26 06:49 UTC` 읽기 전용 `doctor`는 설정·health 항목 10/10, `ready=true`, `desktop_ready=true`, Claude Messages 경로 `native`/`same-wire-native`, 도구·추론·캐시 전달 `passthrough`, 모델 및 자동 압축 창 262,144를 보고했다. 최근 Claude Desktop 요청 12/12건이 HTTP 200이었고 전체 응답 중앙값은 2,217.5ms, 첫 upstream body 청크 중앙값은 39ms, 유효 generation-window 디코드 표본 9건의 중앙값은 112.7 tok/s였다. 최신 표본은 입력 133,267토큰 중 133,189 캐시 입력, 출력 150토큰, HTTP 200/2,033ms, generation-window 추정 97.5 tok/s였다. `first_response_chunk_ms`는 첫 모델 토큰 지연이 아니며 요청 출력 처리율도 디코드 속도가 아니다. 이 최근 관측은 API 왕복의 응답성을 보여주지만 고정 프롬프트 반복 벤치마크나 파일 작업 전체 시간은 아니다.

같은 점검 구간 Strata 서버는 사용자 설정의 AI 전용 RTX 3090 Ti(UUID `GPU-1f5cc5f8-41f5-0817-46b1-548cf1357b8d`, GPU index 1)에서 실행 중이었다. 장치 메모리 23,286/24,564 MiB, 사용률 0%였고 별도 RTX 3090은 Strata 설정 대상이 아니었다. OpenCodex는 로컬 10100, Strata API는 8080에서 수신 중이며 `/status` 기반 doctor는 모델 로드와 Desktop gateway를 준비 상태로 판정했다. 이 점검 구간에 Strata 추론 부하는 관측되지 않았다. 높은 예약 VRAM은 현재 프로필의 실사용이지만 동시 262K 요청이나 장시간 부하에서의 여유를 증명하지 않는다.

Claude Desktop 화면은 133.3k/262.1k(51%), MCP 도구 96개/33.9k 토큰, 자유 공간 약 95.9k로 표시했다. 관리 MCP는 `agent-tools` 2개와 `strata-maintenance` 5개이며 CUA·REA는 필요할 때 검색하는 on-demand 모드다. 나머지 도구 스키마 상당수는 Claude Desktop 내장 기능이다. 사용자 설정에서 제거 가능한 중복은 확인되지 않았고 내장 스키마를 줄일 안전한 앱 설정도 입증되지 않아 손대지 않았다. 자동 압축 버퍼가 창 안에 있으므로 화면 자유 공간은 실제 압축 임계값과 같다고 보지 않는다.

이 경로에서 확인된 잔여 계측 공백은 OpenCodex 요청 페이싱이 꺼져(`enabled=false`) 대기열·동시 요청 수가 `not_tracking`으로 남는다는 점이다. 설치본의 `providerFetch`는 managed native Messages에도 사용되며 `maxConcurrentRequests`를 적용할 수 있다. 현재 `strata` 규칙은 없음(`rules=null`)이다. doctor의 `queued=0`/`in_flight=null`은 페이싱 계층이 보고할 값이 없어 동시 요청이 전혀 없다는 증명이 아니다. 동시성 상한은 고립된 단일 요청에는 간격 제한을 추가하지 않지만, 상한을 넘는 병렬 에이전트 요청은 대기시켜 전체 완료 시간을 늘릴 수 있다. 따라서 단일 3090 Ti의 다중 동시 요청 대기·처리량 병목은 **미측정**이고, 262K 동일 조건의 동시 실행 비교 전에는 상한을 임의로 정하지 않았다.

직전 격리 진단 세션에서는 READY가 화면에 나온 뒤 Desktop에 실행 표시가 남아 있었다. 이후 파일·명령 없이 wrap_up만 요청하자 Claude는 호출 완료를 보고했고, 읽기 전용 화면 관측은 `Claude가 응답을 완료했습니다`로 바뀌어 Stop/실행 표시가 사라진 상태였다. 이번 확인에서도 선택된 대화는 `Claude가 응답을 완료했습니다`였고 `Claude가 응답 중입니다` 및 Stop 표시는 없었다. 이 결과는 완료 상태 불일치와 누락된 wrap_up 사이의 연관 가능성을 지지하지만, 추가 요청이 UI 상태를 갱신했을 수 있어 유일 원인을 증명하지 않는다. 이에 Claude Desktop Code의 계획·파일·도구 작업 완료 후 wrap_up을 호출하라는 한 줄 규칙을 공유 지침에 넣고 사용자 관리 Claude 프로필에 생성했다. 관련 단위 검사 9개가 통과했다. 현재 실행 중인 Code 세션은 재시작하지 않았으므로 새 지침의 세션 로드는 다음 새 세션에서 확인해야 한다.

이번 단계에서는 요청 경로에 반복·번역 병목을 보여주는 근거가 없고, 최근 성공률과 응답 지연도 오류 또는 눈에 띄는 서버 대기를 보이지 않아 OpenCodex·Strata 프로세스를 재시작하거나 GPU 설정을 바꾸지 않았다. 남은 개선 대상은 동시성 계측이며, 설정이 아닌 계측을 추가하려면 OpenCodex 소유 계층이 제공하는 안전한 요청 ID/queue 관측이 먼저 필요하다. Claude Desktop 내부 SSE의 `message_stop` 시각과 요청별 공통 ID는 여전히 수집되지 않아 UI 완료까지의 정확한 지연 원인은 **미확정**이다.

## 2026-10-26 16:06 KST 재확인

읽기 전용 `doctor`에서 연결·모델·컨텍스트·MCP·Claude Desktop 프로필 검사가 10/10 통과했고, Claude Code와 Strata 양쪽의 컨텍스트 창은 262,144였다. Claude Messages는 OpenCodex의 `native`/`same-wire-native` 경로를 사용하며 도구·추론·캐시 필드가 전달 미리보기에서 보존됐다. 최근 Claude Desktop 표본은 12/12 HTTP 200, 응답시간 중앙값 2,217.5ms, 첫 upstream body 청크 중앙값 39ms, generation-window 디코드 중앙값 112.7 tok/s(9건)였다. 최신 기록은 2,033ms, 입력 133,267토큰(창의 50.8%), 캐시 입력 133,189토큰(99.9%), 출력 150토큰, 디코드 추정 97.5 tok/s였다. 이는 짧은 관측에서 직렬 요청 경로의 실패나 큰 게이트웨이 지연을 보여주지 않지만 262K 전체 입력이나 파일 작업 완료시간을 시험한 결과는 아니다.

같은 시점 Strata는 RTX 3090 Ti(UUID `GPU-1f5cc5f8-41f5-0817-46b1-548cf1357b8d`)에서 모델을 로드했고 `serving=1`, `requested=1`, 활동 `idle`, `in_flight=0`이었다. 마지막 엔진 기록은 프롬프트 78 신규 토큰/376.9ms, 생성 150토큰/1,553.7ms였다. OpenCodex의 2,033ms 기록과 엔진 타이밍은 요청 ID로 연결되지 않으므로 둘의 차이를 검증된 프록시 오버헤드로 계산하지 않는다. GPU 메모리는 23,540/24,564MiB로 여유가 약 1,024MiB, 호스트 RAM 여유는 28,847MiB(22.0%)였다. 부하가 없는 상태의 사용률 0%는 성능 여유나 동시 처리량을 증명하지 않는다.

남은 실제 결함 후보는 OpenCodex 페이싱이 꺼져 있어 OpenCodex 안에서 대기 중인 요청을 계측하지 못한다는 점이다. 반면 Strata 자체는 한 요청만 동시에 제공하도록 실행 중이다. 설치된 OpenCodex 페이싱을 `maxConcurrentRequests=1`로 추가하면 동일 GPU에 두 번째 admission gate가 생기며, 해당 구현은 대기열을 최대 60초 보관한 뒤 만료시킨다. 장시간 생성과 병렬 세션에 미칠 영향은 현재 자원 상태에서 시험하지 않았으므로 이 설정을 켜지 않았다. 대형·동시 부하 시험은 VRAM 여유가 약 1GiB뿐인 현재 상태에서 실행하지 않았다. 따라서 단일 요청 경로의 개선이 필요한 병목은 이번 관측에서 확인되지 않았고, 동시 요청의 큐 지연·취소·완료시간은 여전히 **미측정**이다. 추후 병목을 해결할 때는 Strata의 기존 단일 슬롯과 OpenCodex 대기열 중 한 계층을 기준으로 비교한 뒤 설정해야 하며, 두 계층에 중복 제한을 먼저 추가하지 않는다.

## 2026-10-26 실제 250K 요청 및 Desktop 자동 압축·후속 수정

앞선 메모리 순간값만으로 부하 시험을 보류한 상태에서 진행해, 로드된 모델의 현재 단일 슬롯이 유휴인지 확인한 뒤 출력 상한을 제한한 직렬 요청을 실행했다. RTX 3090 Ti만 사용했고 GPU 프로필·448MiB reserve·262,144 컨텍스트·OpenCodex 페이싱은 바꾸지 않았다. 다음은 A/B 성능 향상 수치가 아닌 실제 실행 기록이다.

| API 경유 시험 | 전체 시간 | 신규 입력 / 재사용 입력 | 엔진 프롬프트 / 생성 시간 | 종료 |
| --- | ---: | ---: | ---: | --- |
| 249,963토큰 첫 입력 | 88.303초 | 249,963 / 0 | 87.035 / 1.011초 | HTTP 200, tool_use, message_stop |
| 도구 검색 후 250,644토큰 | 2.729초 | 688 / 249,956 | 2.253 / 0.355초 | HTTP 200, tool_use, message_stop |
| 같은 요청 반복 | 1.732초 | 7 / 250,637 | 1.312 / 0.286초 | HTTP 200, tool_use, message_stop |

각 호출 전후 활동은 idle이었고 Strata 요청 수는 각각 정확히 1 증가했다. 첫 입력의 프리필은 2,872 tok/s였다. 전체 시간에서 엔진 프롬프트·생성 시간을 제외한 나머지는 약 0.12~0.26초지만, 여기에 클라이언트·HTTP·토큰화·정리도 포함되어 OpenCodex 단독 오버헤드라고 부르지 않는다. 짧은 직접/프록시 요청도 둘 다 HTTP 200, 정확한 응답, message_stop, EOF, 유휴 복귀를 통과했으나 두 번째의 캐시 이점 때문에 속도 우열로 계산하지 않았다.

실제 Claude Desktop 3.6556.2.0의 Code 화면(내장 CLI 2.1.308)에서도 격리된 stats.py 구현과 같은 대화의 후속 수정을 실행했다. 첫 구현은 입력 제출부터 CLI Stop hook 종료까지 39.224초, 8개 컨텍스트 파일 전체 읽기와 후속 수정은 146.437초였다. 자동 압축 metadata는 preTokens=246,130, postTokens=8,144, durationMs=42,619이며, 이는 대화 기록 부분의 크기다. 고정 도구·시스템 지침을 합친 다음 실제 요청은 69,440토큰이었다. 압축 요청은 3,636토큰을 생성하며 42.583초, 압축 뒤 첫 모델 요청은 입력 69,440/재사용 16,384토큰으로 21.718초였다. 이번 표본의 큰 비용은 첫 프리필, 압축 요약, 압축 뒤 캐시 재구축이었다.

Desktop은 후속 요청의 제약을 유지해 stats.py 하나만 수정했고 터미널을 호출하지 않았다. 실제 파일의 단위 검사 3개가 통과했고, 100,000개 숫자를 처리하는 추적 메모리 검사는 기존 약 3.81MiB에서 832바이트로 줄어 상수 추가 메모리 조건을 통과했다. 이 메모리 수치는 진단용 함수의 구현 검증이며 LLM 처리량 개선이 아니다. 두 턴 모두 wrap_up 성공 결과와 end_turn/Stop hook 종료가 기록됐고 후속 요청도 일반 Enter로 정상 접수됐다. 최종 실제 화면에는 완료 답변과 입력란이 보였고 실행 중 Stop 버튼은 사라졌다. 화면 완료 시각을 연속 계측하지 않아 UI 완료 지연의 정확한 수치는 주장하지 않는다. Windows 접근성 텍스트는 이전 화면을 계속 반환하는 경우가 있어 실제 스크린샷과 실행 기록으로 대조했다.

재기동 전 16:08:38~16:08:59의 502 세 건은 모두 ECONNREFUSED였다. 새 서버 프로세스는 16:09:34에 시작됐으며 이후 위 요청은 통과했다. 연결 거부 시점과 재기동 시점은 확인했지만 이전 서버가 정지한 원인은 확정하지 않았다. 유지보수 진단의 최근 요청 결과에 failure_summary를 추가해 고정된 upstream_connection_refused 분류와 시각·상태만 반환한다. 원문 오류·자격증명은 반환하지 않고 불명확한 오류를 원인 확정이나 자동 재시도 허가로 사용하지 않는다. 관련 71개 CPU/로컬 HTTP 계약 검사가 15.958초에 통과했고 실제 environment_status 새 인스턴스도 ready=true, desktop_ready=true, context=262144, activity=idle 및 새 필드를 반환했다. 실행 중인 기존 MCP 프로세스는 모듈을 이미 로드했을 수 있으므로 새 인스턴스의 결과와 구분한다.

원시 계측·시도 이력·진단 코드·검증 결과는 C:\Users\luiny\Strata-data\diagnostics\claude-pipeline-20261026-1615 에 보관했다. 첫 probe는 HTTP 전송 전에 잘못된 helper 이름으로 실패했고 이를 보존한 뒤 수정했다. 이번에는 모델 설정의 속도 향상을 주장하지 않으며, 자동 압축 비용을 줄이는 변경과 동일 입력의 반복 비교는 아직 수행하지 않았다. 동시 262K 요청, 수 시간 방치, 재부팅·외부 PC는 이 실행의 검증 범위가 아니다.

### 압축 지침 후보 시험: 공통 설정에 미반영

공식 Claude Code 문서의 Compact instructions 형식에 따라 진단 프로젝트에만 짧은 요약 지침을 두고 같은 8개 파일 부하와 추가 수정을 실행했다. 문서 근거: https://code.claude.com/docs/en/costs#manage-context-proactively . 이번 파일은 과거 답변·코드·합성 데이터·완료 파일 읽기 목록의 반복을 줄이고 최신 제약·검증 근거·남은 행동을 보존하도록 했다. 원래 공통 지침을 바꾸지는 않았다.

후보 실행은 preTokens=250,248, postTokens=8,403, 압축 55.131초였고 요약 요청 출력은 4,793토큰이었다. 앞선 42.619초/3,636토큰보다 개선되지 않았다. 입력 대화와 추가 구현 요구가 동일하지 않아 엄밀한 A/B 인과 비교는 아니며, 속도 개선 근거로 쓰지 않는다. 후속 skip_invalid 키워드 옵션의 선택적 ValueError 처리·기본 계약·다른 예외 전파·기존 단위 검사 3개·상수 메모리 검사는 통과했다. 전체 턴은 166.572초였다.

효과가 확인되지 않아 후보를 공통 설정에 적용하지 않았고 진단 프로젝트의 임시 CLAUDE.md도 제거해 candidate-CLAUDE.md로 증거 폴더에 보관했다. 전처리 probe/검증 입력의 실패와 수정은 attempt-history.md에 남겼다. 따라서 현재 적용한 변경은 최근 연결 오류의 안전한 분류이며, 압축 속도 향상을 주장하지 않는다.

### 겹친 두 대형 요청의 단일 슬롯 대기 검증

입력 250,027/250,644토큰의 두 요청을 OpenCodex로 겹쳐 전송했다. Strata의 serving/requested는 1/1을 유지했고, 활동은 in_flight=1 → 2 → 1 → 0, 실행 요청 수는 22 → 23 → 24로 관측됐다. 첫 요청은 92.505초, 대기한 두 번째 요청은 98.361초에 HTTP 200/message_stop으로 종료됐고 최종 상태는 idle이었다. 첫 요청의 512토큰/max_tokens 종료는 대기를 관측하기 위한 의도된 출력 상한이고, 두 번째는 tool_use로 종료됐다. 실제 도구 실행은 없는 API 스트림 시험이다. 초기 토큰 수 전처리는 tool_choice=none으로 도구 정의가 제외돼 목표 크기보다 작아 실패했으며 생성 전 중단했다. 원래 정의를 유지한 실제 시험과 전처리 실패 기록을 함께 보관했다.

이 결과는 단일 3090 Ti·단일 슬롯에서 대형 요청의 직렬 대기가 동작함을 보이며 두 사용자의 동시 생성 처리량을 증명하지 않는다. 기존 Strata 대기열이 90초 이상 대기한 요청도 정상 처리한 근거가 생겼으므로, 별도의 OpenCodex 동시성 1 제한과 60초 대기 만료를 중복 추가하지 않았다. 원시 결과는 queue-verification.json, queued-first.json, queued-second.json에 있다.

### 새 Desktop MCP 인스턴스 반영 확인

17:13에 같은 진단 폴더의 새 Code 세션을 열어 기존 설정으로 생성된 유지보수 MCP를 실제로 호출했다. 새 Python 프로세스는 17:13:14에 시작됐으며, Code transcript 6a439ae7-556e-4184-8e89-b812240acf58에는 environment_status 정확히 1회, ready=true, desktop_ready=true, context=262144와 새 failure_summary 필드가 기록됐다. 호출 중 파일·설정·명령·재시작 도구는 없었고 17:13:48.200 KST에 Stop hook이 끝났다. 실제 최종 화면의 입력란은 실행 중 Stop 표시가 없는 상태였다. mcp-live-verification.json에 이 확인과 최종 Strata 유휴 상태를 보관했다. 이전 Code 세션이 보유한 구 MCP 프로세스는 강제로 종료하지 않았으며 새 연결부터 개선 코드가 적용됨을 확인했다.
