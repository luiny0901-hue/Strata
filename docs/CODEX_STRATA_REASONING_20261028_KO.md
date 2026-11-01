# Codex → OpenCodex → Strata 추론 단계 점검

2026-10-28, 설치된 OpenCodex 2.92.0과 현재 Unsloth UD-IQ4_XS ON 서버를 확인했다. [OpenAI 공식 문서](https://developers.openai.com/api/docs/guides/reasoning)는 지원하는 추론 값이 모델별로 다르다고 설명한다. 아래 수치는 OpenAI 모델의 능력을 로컬 모델에 부여하는 설정이 아니라 현재 Strata 템플릿과 생각하기 상한의 매핑이다.

## 확인한 결함과 수정

Codex는 Responses의 `reasoning.effort`를 보낸다. OpenCodex의 일반 Anthropic 어댑터는 low/medium/high를 각각 `thinking.budget_tokens` 4096/8192/16384로 변환한다. Strata 프런트엔드는 2048 미만을 low, 8192 미만을 medium, 그 이상을 내부 xhigh로 해석했다. 기존 서버의 실제 생각하기 상한은 별도 `reasoning_budget_tokens=8192`였으므로, UI Low는 native medium으로, Medium·High는 같은 native high와 같은 상한으로 처리됐다.

현재 변경:

- OpenCodex의 해당 Strata 모델에만 `modelReasoningEfforts=low,medium,high`, 기본 medium을 관리 CLI로 저장했다. 다른 공급자 설정과 Codex의 전역 모델·추론 선택은 보존했다.
- Strata 공급자에는 `x-strata-effort-wire: opencodex-low-medium-high-v1` 헤더를 관리 CLI의 좁은 PATCH로 추가했다. 설치된 npm OpenCodex 소스를 직접 수정하지 않았다.
- 기존 `strata_anthropic_effort.py`·알려진 fork 통합 패치를 재사용해 이 헤더가 있을 때만 알려진 세 wire budget을 원래 선택값과 상한으로 변환한다. 기존 `output_config` 형식은 유지하며 명시한 Strata cap·native effort·disabled thinking은 우선한다. 헤더 없는 기존 클라이언트의 동작은 그대로다. native Claude Desktop의 adaptive/effort 경로를 새 budget 형식으로 바꾸지 않는다.
- 기존 운영 helper/patch/tests를 추적 가능한 이 저장소에 포함했다. ON/OFF 실행기도 같은 패치와 tools import 경로를 사용한다. 알려진 V1 패치는 두 통합 구간만 업그레이드하며, 알 수 없는/부분 적용 소스는 거부한다.

| Codex 선택 | Strata 내부 템플릿 | 생각하기 상한 |
|---|---|---:|
| Low / 낮음 | low | 3,072 토큰 |
| Medium / 중간 | medium | 4,096 토큰 |
| High / 높음 | xhigh: Strata의 native high | 8,192 토큰 |

예산은 최대값이다. 간단한 요청이 일찍 끝나면 생각 시간·출력량이 비슷할 수 있으며, 표의 상한만으로 정답률·완료시간 개선을 보증하지 않는다. 현재 ON의 명시적 effort 예산을 재사용한다. 해당 map이 없는 프로필도 Codex 호환 모드에서는 위 기본값을 사용한다. OFF 전체 모델 실행은 이번에 하지 않았다.

## Max·Ultra 표시의 실제 의미

설정된 native ladder는 세 단계지만 **OpenCodex 2.92.0이 합성 Max·Ultra를 자동 추가해 현재 생성 카탈로그에는 low/medium/high/max/ultra가 있다.** 최초 세 개만 기대한 게시 후 검사는 이 동작 때문에 실패했다. 생성 카탈로그를 손으로 수정하거나 다른 모델의 전역 추론 메뉴를 줄이지 않았다. xhigh는 해당 Strata 행에서 제거됐다.

Max는 현재 Strata에서 별도 native 단계가 아니며 high와 같은 내부 xhigh·8,192 상한으로 처리된다. Ultra는 OpenCodex가 자동 위임용으로 표시하는 모드이고 Codex 클라이언트는 wire에서 max로 변환한다. 실제 자동 위임 실행은 이번에 시험하지 않았다. 따라서 Max·Ultra를 더 깊은 별도 로컬 모델 추론으로 설명하면 안 된다. 세 native 값 이외의 합성 표시를 완전히 숨기는 변경은 하지 않았다.

**2026-10-31 갱신**: 사용자 요청으로 Strata 공급자에 `modelSuppressSyntheticMax=true`(모델 키 `qwen3.8-flash-next-unsloth-ud-iq4_xs`)를 관리 API `POST /api/providers`로 적용했다. 카탈로그는 즉시 재생성되어 Strata 행은 `low/medium/high/ultra`가 됐고 Max 선택지는 사라졌다. 원본 공급자 백업: `C:/Users/luiny/.claude/backups/strata-provider-pq_a0dwm.json`. 같은 변경 시각 다른 모델 행의 사다리는 그대로였다(모델별 표시는 카탈로그가 이미 유지). Ultra는 2.92.0에서 조건 없이 추가되어 남으며 끌 설정이 없다. Codex 보통 왕복은 재실행해 `ok`를 확인했고, `max`로 하위 작업을 여는 경로는 미확인이다. Codex 데스크톱·클라이언트는 시작 시 카탈로그를 읽어 재시작 후 반영된다.

## 검증·실행 기록

- 설치된 `createAnthropicAdapter.buildRequest()`를 실제로 호출해 네트워크 없이 wire body/header를 수집했다. 알려진 fork의 실제 `effort_kwargs`·`budget_effort`와 기존/수정 helper를 대조해 low/medium/high의 기존 medium/xhigh/xhigh, 수정 low/medium/xhigh 및 3072/4096/8192 상한을 확인했다.
- helper/patch 9개와 프로필/실행기 관련 9개: `python -X utf8 -m unittest tools.test_strata_anthropic_effort tools.test_strata_iq4xs_profiles -q`, **18개/0.126초 통과**. 최초 9개 실행에서는 복사한 이전 검사의 인자 없는 호출 문자열 기대값이 새 header keyword에 맞지 않아 1개 실패했다. 실제 새 호출/header 계약을 확인하도록 해당 기대값을 갱신했고 기록을 남겼다. 구문·재적용 멱등성·`git diff --check`와 ON/OFF import 경로 확인도 통과했다.
- 기존 supervisor에 `codex-strata-effort-20261028-1`을 한 번 제출해 유휴 상태에서 Strata를 재시작했고 ready를 확인했다. 프록시·Codex는 재시작하지 않았다.
- 실제 `10100/v1/responses`로 low/medium/high/max 네 번의 같은 짧은 산술 요청을 보냈다. 전부 HTTP 200·completed·정답 703·도구 0회였다. Low의 실제 서버 로그에서 `budget 3072`도 확인했다. 이 작은 요청은 대부분 캐시를 재사용했으며 속도/품질 비교가 아니다. 응답의 reasoning_tokens=0은 서버 thinking 로그와 일치하지 않아 실제 생각 토큰 수 증거로 사용하지 않았다.
- 다른 공급자 설정은 그대로이고 카탈로그 갱신 시 네 Antigravity 행의 `opencodex_multi_agent_version_origin` 출처 필드만 갱신됐다. 이 행들의 추론 단계는 바뀌지 않았다. 카탈로그 refresh는 committed였지만 fallback/provider-auth 경고가 있어 모든 공급자의 현재 인증을 확인했다고 하지 않는다.

실제 Codex GUI 선택창·262K 작업·장시간 품질 차이·Ultra 자동 위임은 미검증이다. [Codex 공식 설정 문서](https://learn.chatgpt.com/docs/config-file/config-reference)는 `model_catalog_json`이 시작 시 읽힌다고 명시한다. **Codex를 재실행하고 해당 Strata 모델을 다시 선택**해 갱신된 카탈로그를 사용한다.

## 2026-11-01 갱신: 매우 높음·최대 단계 추가

사용자 요청으로 사다리를 5단계로 확장했다. 근거: ON 서버 로그에 `thinking budget reached (8192)` 조기 종료가 실제 관측되어 상한 확대 실익이 확인된 요청 유형이 있었다.

- `tools/strata_anthropic_effort.py`의 `EFFORT_LEVELS`·Codex 라벨 매핑을 low/medium/high/xhigh/max로 확장했다. OpenCodex 어댑터의 `reasoningBudget`(low 4096/medium 8192/high 16384/xhigh 24576/max 32000)을 그대로 라벨 역매핑에 사용했고 기본 상한은 3072/4096/8192/**16384/24576**다. 헤더 표식 문자열(`opencodex-low-medium-high-v1`)은 호환성 유지로 그대로 둔다.
- ON 템플릿 두 곳(운영 루트·체크아웃)의 `anthropic_effort_budgets`에 `xhigh: 16384`, `max: 24576`을 추가했다(전역 `reasoning_budget_tokens: 8192`는 유지 — 단계별 상한만 확장). OFF·게이트웨이 외 설정은 그대로다. OpenCodex 사다리는 소유 설정기로 5단계 재게시(백업 `strata-provider-jndo0496.json`).
- 운영 루트의 실행 중 코드(`C:/Users/luiny/Strata/tools/strata_anthropic_effort.py`)가 이전 3단계판이었어서 수정본으로 동기 복사한 뒤 supervisor 재시작(`effort-ladder-5-20261101-1`, ready)했다. 재시작 로그: `Anthropic reasoning budgets: low=3072, medium=4096, high=8192, xhigh=16384, max=24576 tokens`.
- 실측: Codex 라벨 방식(`thinking.enabled` 24576/32000) 요청이 서버에서 각각 `budget 16384`·`budget 24576`로 처리됨을 supervisor 로그로 확인했다. 네이티브 어댑티브 방식은 OpenCodex가 예산 형태로 바꾸지 않으면 서버 전역 기본(8192)이 유지되므로 상위 단계를 쓰려면 Codex 경로처럼 라벨 예산이 전달되는 형태로 요청해야 한다(어댑티브 라벨 전용 경로는 미지원 상태 그대로).
- 검사: `tools.test_strata_anthropic_effort`(5단계 라벨 매핑), `tools.test_strata_client_settings`(115 포함 묶음), `tools.test_strata_iq4xs_profiles`(ON 사다리 불변 검사 추가) 통과. 템플릿 재적용 멱등 확인.
- 사용: Codex는 재실행해 카탈로그를 다시 읽으면 Strata 행에 매우 높음·최대가 노출된다. Desktop Code의 선택기 노출은 화면 확인 전(미검증). 쉬운 질문은 상한과 무관하게 일찍 끝나며, 상위 단계 도달 시 대기 상한은 16384≈약 172초, 24576≈약 259초다. 상위 단계의 품질 이득은 여전히 미측정이다.

## 2026-11-01 늦은 시각: 네 경로 상위 단계 인식 검증과 Claude 경로 상한 수정

사용자 요청으로 매우 높음·최대의 4경로 인식 여부를 실측했다.

- **서버**: `budget 16384`까지 생각한 로그(16,342토큰까지 사용)와 `budget 24576` 캡 로그가 서버 로그에 실제로 남아 상위 예산 처리가 확인됐다. Codex 라벨 방식은 earlier절에서 이미 확인.
- **Codex CLI·ChatGPT Desktop(Responses 표면)**: 카탈로그는 이미 low..max+ultra 6종 노출 중(`--check`의 advertised 확인). OpenCodex가 Strata를 어댑티브 모델로 처리하도록 `modelCapabilities.<model>.supportsReasoningEffort=true`를 단일 공급자 POST로 추가했다(기존 inputModalities 보존, 즉시 반영·재시작 불필요). 이후 `reasoning.effort=xhigh/max`가 어댑티브 라벨로 전달되고 OpenCodex 로그의 requestedEffort에 `xhigh`·`max`가 그대로 찍혔다. 같은 프롬프트의 생각 분량이 previous(8192 고정) 대비 194초/107초로 길어져 상위 예산 동작과 일치했다. 단 로그의 표면 필드가 없는 요청은 귀속을 강하게 보지 않는다.
- **Claude CLI·Desktop Code(Anthropic 표면)**: `--effort xhigh|max`가 `Effort 'xhigh' exceeds the cap ...; using 'high'`로 강등되는 것을 발견. 원인은 Claude Code 상한 설정 두 곳: `~/.claude/settings.json`의 `maxEffortLevel: "high"`와 커스텀 모델 능력 미선언. 공식 문서 기준 `maxEffortLevel`은 `low|medium|high|xhigh|max`를 받고 능력 키는 `xhigh_effort`·`max_effort`다. 이를 반영해 `maxEffortLevel`을 `max`로, `ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES`를 `effort,xhigh_effort,max_effort,thinking`으로 수정했다(백업 없이 사용자 설정 최소 병합; 강등 경고 사라짐 확인, exit 0). 단 `ANTHROPIC_BASE_URL` 게이트웨이에서 능력 변수가 UI 상한까지 여는지는 문서에 보장돼 있지 않아, 이 경로가 실제 서버에서 `budget 16384/24576`를 내보내는지는 새 Desktop 세션에서 별도 확인이 필요하다(현재까지 해당 예산 로그는 Responses·직접 Messages 시험에서 확인).
- 수정 파일: `~/.claude/settings.json`(2키), OpenCodex `providers.strata.modelCapabilities`(관리 API POST, 백업 없음·되돌리기는 같은 필드 제거). Strata/OpenCodex/Desktop 재시작 없음. 검사 변경 없음(설정·실행 검증만). 커밋 없음.

## 2026-11-01 심야: 자율 코딩 장기 운전 기준 재조정 (출력 65536, max 32768)

사용자 승인(“그렇게하고…개선해”)으로 두 값을 올렸다. 근거: 커뮤니티는 기본 중간·필요 시 승격을 권하고, Qwen3-Coder 예제는 32,768 생성을 사용. 최대 단계가 답변 자리 7,400만 남기는 문제가 이 환경의 실제 제약이어서 합산 상한을 함께 확대했다.

- **전체 출력(생각+답변) 기본값 32,000→65,536**: `~/.claude/settings.json`의 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`와 설정기 재투영(`--codex-only` 아님, 기본 경로; 백업 `strata-provider-vzx1tfc8.json`)으로 반영. `--check`의 claude_output·출력 표시 65536 확인. 요청이 `max_tokens`를 명시하지 않는 경로에 적용되며, 명시 요청(예: Claude의 32,000 고정 경로가 있다면)은 그 값을 따른다. 초과분은 `fit_max_tokens` 자동 축소가 그대로 안전장치.
- **사다리 max 24,576→32,768**: ON 템플릿 두 곳과 `CODEX_DEFAULT_BUDGETS`(체크아웃·운영 루트 동기). 최종 단계표: low 3072 / medium 4096 / high 8192 / xhigh 16384 / max 32768, 각 단계 답변 최소 확보분은 62,464→32,768로 전 단계 종전보다 확대. 전역 `reasoning_budget_tokens: 8192` 유지.
- 반영: supervisor 재시작(`output-65k-ladder-20261101-1`, ready). 시작 로그에 `low=3072 … max=32768` 로드 확인. 생성 프로필에도 같은 값 확인.
- 검증: `budget 32000` 요청에서 `thinking capped at … (budget 24576)` 규칙과 동일한 자동 축소 로그가 새 상한으로 동작 — 최종 확인된 로그는 `(budget 32768)` 캡 동작(생각 24,000에서 답 자리 확보). Codex 라벨(32000) 방식은 max 라벨로 처리되며, 어댑티브+`output_config.effort:max` 단독 요청은 그 턴에서 생각 미생성(로그 없음) — 이 경로까지의 예산 적용은 Desktop 화면에서 별도 확인 필요(미검증).
- 검사: 사다리·프로필·설정 묶음 44개 통과, 템플릿 재적용 멱등. 시간 상한(생각만 최대 32,768 ≈ 약 340초)과 답변 최대 약 32,768은 요청당 상한이며 품질 이득은 미측정. 커밋 없음. 되돌리기는 설정 2곳(출력 env·사다리 max)을 원값으로 되돌리고 같은 재시작 경로.

## 다른 PC에서 동일 설정

먼저 이 저장소의 ON/OFF 실행기로 Strata를 시작하고, OpenCodex에서 `strata`가 같은 서버와 모델을 가리키는지 확인한다. 그다음 설치된 관리 CLI를 사용한다.

```powershell
ocx provider edit strata --headers '{"x-strata-effort-wire":"opencodex-low-medium-high-v1"}' --json
ocx models set strata/qwen3.8-flash-next-unsloth-ud-iq4_xs --reasoning-efforts low,medium,high --default-reasoning-effort medium --json
```

다른 모델로 바꿀 때 이 결과를 자동 적용하지 말고 해당 템플릿과 wire 지원을 확인한다. 원복 시 저장한 공급자 header와 두 모델별 effort 필드만 관리 API로 복원한다. 전체 config PUT·npm 파일 덮어쓰기·생성 카탈로그 수동 수정으로 되돌리지 않는다.

원본·관리 영수증·wire 비교·실제 응답·재시작/게시 백업: `C:/Users/luiny/Strata-data/diagnostics/codex-strata-effort-20261028/`. 커밋·푸시는 하지 않았다.
