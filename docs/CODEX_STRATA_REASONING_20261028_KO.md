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

## 검증·실행 기록

- 설치된 `createAnthropicAdapter.buildRequest()`를 실제로 호출해 네트워크 없이 wire body/header를 수집했다. 알려진 fork의 실제 `effort_kwargs`·`budget_effort`와 기존/수정 helper를 대조해 low/medium/high의 기존 medium/xhigh/xhigh, 수정 low/medium/xhigh 및 3072/4096/8192 상한을 확인했다.
- helper/patch 9개와 프로필/실행기 관련 9개: `python -X utf8 -m unittest tools.test_strata_anthropic_effort tools.test_strata_iq4xs_profiles -q`, **18개/0.126초 통과**. 최초 9개 실행에서는 복사한 이전 검사의 인자 없는 호출 문자열 기대값이 새 header keyword에 맞지 않아 1개 실패했다. 실제 새 호출/header 계약을 확인하도록 해당 기대값을 갱신했고 기록을 남겼다. 구문·재적용 멱등성·`git diff --check`와 ON/OFF import 경로 확인도 통과했다.
- 기존 supervisor에 `codex-strata-effort-20261028-1`을 한 번 제출해 유휴 상태에서 Strata를 재시작했고 ready를 확인했다. 프록시·Codex는 재시작하지 않았다.
- 실제 `10100/v1/responses`로 low/medium/high/max 네 번의 같은 짧은 산술 요청을 보냈다. 전부 HTTP 200·completed·정답 703·도구 0회였다. Low의 실제 서버 로그에서 `budget 3072`도 확인했다. 이 작은 요청은 대부분 캐시를 재사용했으며 속도/품질 비교가 아니다. 응답의 reasoning_tokens=0은 서버 thinking 로그와 일치하지 않아 실제 생각 토큰 수 증거로 사용하지 않았다.
- 다른 공급자 설정은 그대로이고 카탈로그 갱신 시 네 Antigravity 행의 `opencodex_multi_agent_version_origin` 출처 필드만 갱신됐다. 이 행들의 추론 단계는 바뀌지 않았다. 카탈로그 refresh는 committed였지만 fallback/provider-auth 경고가 있어 모든 공급자의 현재 인증을 확인했다고 하지 않는다.

실제 Codex GUI 선택창·262K 작업·장시간 품질 차이·Ultra 자동 위임은 미검증이다. [Codex 공식 설정 문서](https://learn.chatgpt.com/docs/config-file/config-reference)는 `model_catalog_json`이 시작 시 읽힌다고 명시한다. **Codex를 재실행하고 해당 Strata 모델을 다시 선택**해 갱신된 카탈로그를 사용한다.

## 다른 PC에서 동일 설정

먼저 이 저장소의 ON/OFF 실행기로 Strata를 시작하고, OpenCodex에서 `strata`가 같은 서버와 모델을 가리키는지 확인한다. 그다음 설치된 관리 CLI를 사용한다.

```powershell
ocx provider edit strata --headers '{"x-strata-effort-wire":"opencodex-low-medium-high-v1"}' --json
ocx models set strata/qwen3.8-flash-next-unsloth-ud-iq4_xs --reasoning-efforts low,medium,high --default-reasoning-effort medium --json
```

다른 모델로 바꿀 때 이 결과를 자동 적용하지 말고 해당 템플릿과 wire 지원을 확인한다. 원복 시 저장한 공급자 header와 두 모델별 effort 필드만 관리 API로 복원한다. 전체 config PUT·npm 파일 덮어쓰기·생성 카탈로그 수동 수정으로 되돌리지 않는다.

원본·관리 영수증·wire 비교·실제 응답·재시작/게시 백업: `C:/Users/luiny/Strata-data/diagnostics/codex-strata-effort-20261028/`. 커밋·푸시는 하지 않았다.
