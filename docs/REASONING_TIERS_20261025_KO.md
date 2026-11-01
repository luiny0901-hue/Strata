# Low·Medium·High 추론 수준 — revision23

Strata의 기존 세 추론 지침에 서로 다른 생각하기 상한을 적용한다. Low의 상한이 Medium보다 높았던 코딩 프리셋을 수정한다. Codex의 빠른 처리·균형·깊은 검토라는 선택 취지를 현재 모델이 지원하는 지침과 예산으로 제공하며, OpenAI 모델의 내부 구현이나 같은 지능을 재현했다는 의미는 아니다.

| 선택 | 생각하기 지침 | 기본 상한 | 용도 |
| --- | --- | ---: | --- |
| Low | 짧고 집중해서 결론 도출 | 3,072 | 단순 조회, 좁은 수정, 빠른 도구 판단 |
| Medium | 작업에 필요한 만큼 검토, 불필요한 확장 억제 | 4,096 | 일반 구현·수정·설명 |
| High | 가정 검증, 대안 비교, 일관성 검토 | 8,192 | 복잡한 설계·디버깅·동시성·보안 검토 |
| Default | 작업에 따라 위 세 수준 중 자동 선택 | 선택된 수준과 같음 | 자동 운영 |

상한은 채워야 하는 목표 토큰 수나 고정 응답 시간이 아니다. 쉬운 작업은 세 수준 모두 일찍 끝날 수 있고, 실제 시간 순서가 바뀔 수도 있다. High는 Strata의 기존 `xhigh` 지침을 사용하며 별도 모델을 불러오지 않는다. [OpenAI의 추론 수준 설명](https://developers.openai.com/api/docs/guides/reasoning)도 작업 난도에 따라 추론량이 달라지는 것으로 설명한다.

## 적용 범위

코딩 프리셋의 공통 정책은 `tools/opencode_runtime_assets.py`의 `AGENT_REASONING_BUDGETS` 한 곳에서 관리한다. 로컬 `apply-opencode`, 복구 설정기, 외부 클라이언트 설치기가 같은 정책을 사용한다. 범용 플러그인의 미설정 경로와 서버의 다른 클라이언트 기본값은 바꾸지 않는다.

수동 선택은 사용자가 고른 수준을 유지하고 Default만 기존 로컬 규칙으로 자동 선택한다. 추가 분류 모델 호출이나 자동 재시도는 없다. 질문·실행 구분, 권한, 도구 중복 방지, 취소와 압축은 기존 정책을 유지한다.

요청에 직접 지정한 `reasoning_budget_tokens`는 0·null을 포함해 보존한다. 0은 서버가 무제한으로 해석하므로 프리셋보다 우선한다. 상한은 서버의 기존 생각하기 마무리 경로를 사용한다. 전체 출력 한도32,000과 도구 인자·코드·파일 크기를 줄이지 않는다. 제목·압축 등 보조 요청에는 새 상한을 강제로 적용하지 않는다.

## 실제 측정

진단 자료는 `C:\Users\luiny\Strata-data\diagnostics\reasoning-tiers-20261025`에 보존한다. 실행 중인 같은 Strata 서버·모델·RTX3090Ti를 사용하며 서버와 모델을 다시 시작하지 않는다. 같은 입력 메시지·temperature0·seed42·전체 출력 한도12,288로 비교한다. 세 수준의 순서를 회차마다 바꾸고 프롬프트 캐시 예열을 별도로 표시한다.

측정 지연은 Strata의 첫 답변/도구 인자와 생성 완료까지다. Rider가 화면에 표시한 시각이나 전체 프로젝트 완료 시간이 아니다. 추론 토큰 수는 생성 문자열을 다시 인코딩한 추정치이며 예산 마무리 토큰 때문에 상한보다 조금 많을 수 있다.

각 수준·문제별 새 설정2회 중앙값이다. Low 후보의 사전 시험3회씩은 아래 시간 중앙값에서 제외하고 정확도 확인에 포함한다.

| 문제 | Low | Medium | High |
| --- | ---: | ---: | ---: |
| 코드: 첫 답변/도구 인자 | 3.28초 | 5.12초 | 17.78초 |
| 계획: 첫 답변 | 24.27초 | 34.52초 | 56.98초 |

Low 계획 문제 완료 시간 중앙값은 기존39.01초에서 새 설정24.43초로 약37.4% 짧았다. 각2회 비교로, 이 문제·실행 조건의 관측 결과다. 단순 코드 문제는 상한에 도달하지 않았으므로 그 시간 차이는 상한 조정 효과로 계산하지 않는다.

직접 생성33회가 모두 정답·정상 완료 검사를 통과했다. 새 Low는 사전3회와 비교2회의 계획 문제에서5/5 정답이었다. 각 수준의 약245K 입력 코드 생성1회씩도56개 검사를 통과했다.

긴 입력의 실제 프롬프트 토큰 수: low 245,374, medium 245,370, high 245,344.

긴 입력 검증의 최초 `long-selected`와 바깥 `run_matrix.py`는 종료코드1이었다. High가 생성한 정상 함수의 선행 docstring을 기존 AST 검사기가 거부한 오탐이다. 함수 내부의 선행 문자열 설명만 허용하도록 검사기를 수정했고 임의 표현식·호출·import 차단은 유지했다. 원래 결과·오류·로그·matrix 종료코드는 수정하지 않았다. 모델 재요청 없이 저장된 동일 코드3개를 다시 검사해 각56개 검사를 통과했으며 `long-selected-recheck.json`에 원본 해시와 재검증 결과를 별도로 보존한다. 기존 검증 모듈의4개 회귀 검사도 통과했다.

Node74개·Python77개와 서버 생각하기 예산16개 검사(총93개), 실제 ACP→Strata 계산·후속 요청10회, 스크립트 ACP 로컬·외부 선택20회가 통과했다. 자동 압축8K·262K, 요청·스트림 취소, 재연결, 늦은 재개6개 ACP 시나리오도 통과했다. 압축·취소 시나리오는 스크립트 모델 계약 검사이며 실제262K 압축/GPU 취소나 Rider 버튼 검증으로 표시하지 않는다.

주요 명령은 `node --test tools/test_automatic_effort.mjs tools/test_output_recovery.mjs tools/test_tool_dedup.mjs tools/test_task_stream.mjs tools/cua-driver/opencode-request-lifecycle.test.mjs`, `python -X utf8 -m unittest tools.test_iq4xs_opencode_setup tools.test_remote_agent_client tools.test_opencode_runtime_assets tools.test_opencode_session_recovery tools.test_configure_opencode_cua_automation serve.test_server.EffortAtTheEnd serve.test_server.ConfigReasoningEffort`, `python -X utf8 -m unittest serve.test_server.ThinkingBudget`다. ACP 실행 명령과 전체 순서는 진단 폴더의 `run_matrix.py`·`publish.py`·각 로그에 보존한다.

재설치 ZIP과 로컬 helper의 실제 격리 설정 결과, 관련 없는 파일/개인 프로필 보존 여부, 현재 설정·최종 서버 유휴 상태는 `package-verification.json`, `local-helper-verification.json`, `final-verification.json`으로 확인한다. 이 기록이 없으면 해당 게시 검증을 완료로 판단하지 않는다.

## 검증과 한계

코드 문제는 함수의 음수·수량0·할인·배송비 규칙과56개 검사를 확인한다. 계획 문제는10개 모듈의 의존성과 비용을 주고 가능한1,024개 조합을 독립적으로 검사한 최적 비용24와 대조한다. 이 한정된 문제의 성공을 모든 프로그램·게임의 정확도 보장으로 해석하지 않는다.

기존 Low2,048과 Medium2,048의 오답 및 이전 측정 실패 기록은 [revision22 보고서](THINKING_BOTTLENECK_20261025_KO.md)에 남겨 둔다. 새 후보는 Low3,072이며 실패한2,048 설정을 다시 적용한 것이 아니다. 코드 문제처럼 상한에 도달하지 않은 경우의 시간 차이를 예산 축소 효과라고 주장하지 않는다.

설치된 OpenCode2.0.22 ACP 경로에서 수동 선택·Default·후속 요청과 실제 서버로 전달된 예산을 확인한다. Rider 메뉴 직접 클릭, 외부 PC·macOS 실기, OpenAI 모델과의 품질 비교는 이 검증에 포함하지 않는다.

현재 OpenCode/ACP 연결은 생성 당시의 플러그인 옵션을 사용하므로 진행 중인 작업을 마친 뒤 다시 연결한다. Strata 서버를 다시 시작할 필요는 없다. 재설치·외부 PC는 최신 ZIP을 풀고 START-AGENT에서 연결 설정을 갱신하면 revision23 정책이 적용된다.
