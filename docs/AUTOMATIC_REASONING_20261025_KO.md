# Default 자동 추론 수준 — 2026-10-25

이 문서는 revision21 도입 당시의 검증 기록이다. 이후 [추론 병목 측정](THINKING_BOTTLENECK_20261025_KO.md)에 따라 revision22에서 Medium의 기본 추론 예산만4,096으로 조정했다. 현재 revision23의 Low3,072·Medium4,096·High8,192 정책과 검증 범위는 [추론 수준 보고서](REASONING_TIERS_20261025_KO.md)를 따른다. 아래 무수정·미지정 예산 설명은 도입 당시 기록이며 현재 코딩 프리셋의 예산 정책과 구분한다.

사용자 요청에 따라 None을 선택 목록에서 제거하고 Default를 자동 선택으로 바꿨다. 목록은 **Low·Medium·High·Default**다. 모델·서버가 원래 제공하던 고정 기본값 기능을 OpenCode 출력 복구 플러그인의 선택형 `automaticEffort:true`로 확장했다. 범용 플러그인의 기본 경로는 자동 선택을 켜지 않는다.

## 선택 규칙

| 선택 | 현재 동작 |
| --- | --- |
| Low | 사용자가 직접 고른 Low를 유지 |
| Medium | 사용자가 직접 고른 Medium을 유지 |
| High | 사용자가 직접 고른 High를 유지; 서버 내부 `xhigh`와 같음 |
| Default | 최신 사용자 작업의 범위·복잡도·위험도를 기준으로 Low·Medium·High 중 자동 선택 |

자동 선택은 추가 LLM 호출이 없는 로컬 규칙이다. 단순 목록·버전·상태 확인·좁은 오탈자 수정은Low, 일반 구현·설명은Medium, 설계·여러 모듈 변경·동시성·보안·원인 불명 오류 분석 등은High를 선택한다. 긴 요청, 내용 없는 요청, 요약만 남은 복구 상태는High로 처리한다. 짧은 “그래”, “이어서 해줘”, “그 부분도 고쳐줘” 등은 이전 작업의 수준을 유지한다. 명확한 새 단순 작업은 낮은 수준을 선택할 수 있다.

이 판단은 질문을 실행 요청으로 바꾸는 기능이 아니다. 실행 권한·질문/작업 구분·취소·GUI 승인은 기존 정책을 따른다. 코드 펜스와 인용 로그의 단어를 새 작업 지시로 취급하지 않는다. 규칙이 모든 문장과 전문 분야를 정확히 이해한다고 보장하지 않으므로, 판단이 맞지 않는 경우 수동 Low·Medium·High를 선택할 수 있다.

실행 중인 같은 사용자 작업의 도구 왕복에서는 결정한 수준을 유지한다. 세션별 최대64개의 수준·사유만 메모리에 두고 원문·코드·도구 결과는 보관하지 않는다. 프로세스 재시작으로 상태가 없어지면 최근 사용자 요청으로 복구하며 요약만 확인되면High를 사용한다. 압축·제목 등 보조 생성의 기존 설정은 변경하지 않는다.

현재 선택은 OpenCode의 `model.variant`로 구분한다. 문자열 인자로 Default와 수동 High를 추측하지 않으므로 예전 개인 프로필의 고정 `reasoning_effort:high`가 남아 있어도 Default만 자동으로 덮어쓴다. 수동 선택 경로는 요청 본문을 읽거나 다시 직렬화하지 않는다. 요청·서버의 최대 출력과 추론 토큰 예산도 바꾸지 않는다. None은 UI에서 제거했으며 서버 API의 기존 추론 끄기 기능과 과거 백업 형식은 다른 클라이언트 호환성을 위해 유지했다.

지원 경로는 설정한 Strata 공급자의 `/chat/completions` JSON 요청이다. 다른 공급자와 확인하지 않은 전송 방식에는 자동 수정을 적용하지 않는다.

## 검증 결과

진단 폴더: `C:\Users\luiny\Strata-data\diagnostics\adaptive-reasoning-20261025`.

- 설치된 OpenCode 2.0.22 ACP에서 로컬·외부 클라이언트 프리셋 각각10회, **실제 Strata 생성20회**를 통과했다. None이 선택 목록에 없고 선택 요청도 거부되는지 확인했다. Default의 단순 작업→Low, 일반 작업→Medium, 복잡한 작업→High, 후속 요청→High 유지, 수동 세 수준과 후속 요청을 확인했다.
- 각 사용자 요청은 생성 요청1회였다. 자동 분류를 위한 추가 모델 요청은 없었다. 실제 모델의 계산 정답과 후속 변경 정답, 전송된 `reasoning_effort`, 추론 출력과 정상 완료를 확인했다. 시험 도구의 출력 한도는2048이며 실제 사용자 설정에는 적용하지 않았다.
- 실제 서버의 `--tail-role-token` 설정과 수준 변경 후 사용량의 캐시 재사용을 확인했다. 짧은 대화에서 재사용이 유지된 근거이며, 새262K GPU 성능 측정으로 확대해 해석하지 않는다.
- 스크립트 모델의 로컬·외부 선택 검사도 각각10회 통과했다. 이 결과는 실제 생성과 구분한다.
- Node70개, Python77개 검사와 기존 ACP 생명주기6개 시나리오가 통과했다.8K·262K 반복 자동 압축, 요청 취소, 스트림 취소, 재연결, 늦은 재개를 포함한다.262K 압축은 스크립트 사용량 기반 계약 검사다.
- CPU 합성 요청7회씩 측정한 Default 본문 처리 중앙값은4KiB 약0.34ms,1MiB 약3.11ms,16MiB 약42.33ms였다. 짧은 분류 문장 반복의 평균은약0.0003ms였다. GPU 생성 시간이나 실제262K 토큰 입력 지연으로 표시하지 않았다. 원시 표본은 `routing-overhead.json`에 남겼다.

```powershell
node --test tools/test_automatic_effort.mjs tools/test_output_recovery.mjs tools/test_tool_dedup.mjs tools/test_task_stream.mjs tools/cua-driver/opencode-request-lifecycle.test.mjs
$env:PYTHONPATH='tools'
python -X utf8 -m unittest tools.test_iq4xs_opencode_setup tools.test_remote_agent_client tools.test_opencode_runtime_assets tools.test_opencode_session_recovery tools.test_configure_opencode_cua_automation serve.test_server.EffortAtTheEnd serve.test_server.ConfigReasoningEffort
```

현재 PC와 재설치·외부 PC용 설치기는 같은 목록·플러그인을 사용한다. 로컬 `apply-opencode`는 플러그인을 먼저 준비한 뒤 설정을 게시한다. 설치본 helper의 다른 차이는 보존하고 이번 두 변경만 반영한다. 외부 설치기는 revision21이다. 일반·개인 ZIP의 격리 설치·회귀 검사와 관련 없는 항목/개인 프로필의 바이트 보존 결과는 `package-verification.json`에, 전역 설정·Rider ACP·개인 프로필·서버 상태는 `final-verification.json`에 남긴다.

현재 열려 있는 OpenCode/ACP는 이전 플러그인을 이미 읽었으므로 진행 중인 작업을 마친 뒤 연결을 다시 시작하고 **Default**를 선택한다. 새 설정에서도 수동 High 등을 선택하면 자동으로 전환하지 않는다. Strata 서버와 모델은 재시작하지 않았다.

Rider 화면에서 메뉴를 직접 클릭하는 시험, 외부 PC·macOS 실기, 복잡한 프로젝트의 코드 품질 우열과 모든 말투의 분류 정확도는 이번 검증 범위가 아니다. 이전 검증 기록과 원시 결과는 덮어쓰거나 삭제하지 않았다.
