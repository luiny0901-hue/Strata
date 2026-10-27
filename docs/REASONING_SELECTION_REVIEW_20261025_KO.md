# 추론 수준 선택 점검 — 2026-10-25

이 문서는 자동 선택 도입 전의 검증 기록이다. 이후 사용자 요청으로 None을 선택 목록에서 제거하고 Default를 자동 선택으로 바꿨다. 현재 동작은 [자동 추론 수준](AUTOMATIC_REASONING_20261025_KO.md)을 따른다.

현재 PC의 OpenCode 2.0.22에서 Rider와 같은 ACP 선택 경로를 통해 `None`·`Low`·`Medium`·`High`를 바꾸고 실제 실행 중인 Strata까지 생성 요청을 전달했다. 네 수준과 후속 수정 요청은 정상 동작했다. 지원되는 항목만 선택할 수 있게 해 달라는 후속 요청에 따라 전역 설정의 선택 목록을 `None → Low → Medium → High` 순서로 통일했다. 저장된 기본 추론 수준과 다른 모델 설정은 보존했다.

저장소의 `tools/iq4xs_opencode_setup.py`에는 `low/medium/high/xhigh`가 남아 있었다. 이 모델에서 `high`와 `xhigh`는 같은 내부 수준이므로 중복이고 `none`은 누락되어 있었다. 이를 `none/low/medium/high`로 수정했다. 현재 PC의 설치본 helper와 외부 PC용 설치기는 이미 이 네 수준을 사용하고 있었으므로 동작을 유지하고 회귀 검사와 문서를 보완했다.

## 실제 동작

| 선택 | 전달되는 `reasoning_effort` | Strata 내부 처리 | 실제 생성 |
| --- | --- | --- | --- |
| None | `none` | `enable_thinking:false` | 추론 출력0자, 정답·후속 요청 PASS |
| Low | `low` | 짧고 집중된 추론 지침 | 추론 출력 확인, 정답·후속 요청 PASS |
| Medium | `medium` | 작업에 필요한 만큼 추론하는 지침 | 추론 출력 확인, 정답·후속 요청 PASS |
| High | `high` | 템플릿의 `xhigh` 지침 | 추론 출력 확인, 정답·후속 요청 PASS |
| Default | 선택 해제 | 저장된 모델 body → 서버 기본값 | 시험용 기본값 High 상속 PASS |

`High`와 별도 `XHigh`가 서로 다른 성능을 제공하는 구조는 아니다. 각 수준에 고정된 추론 토큰 수를 배정하지도 않는다. 요청·서버의 추론 예산과 최대 출력 한도는 별도로 적용된다. 쉬운 문제에서 Medium과 High의 추론 길이가 같아도 선택이 무시된 증거는 아니다.

## 검증

진단 폴더: `C:\Users\luiny\Strata-data\diagnostics\reasoning-selection-review-20261025`.

- 현재 서버는 `qwen3.8-flash-next-unsloth-ud-iq4_xs`,262144 컨텍스트, 실행 중인 Strata PID12032로 확인했다. 새 서버·모델을 띄우거나 기존 서버를 재시작하지 않았다.
- 설치된 OpenCode ACP의 `session/new`가 네 수준과 Default를 `thought_level` 선택 항목으로 제공하는지 확인했다.
- `session/set_config_option`으로 수준을 선택하고 같은 모델을 다시 동기화해도 선택이 유지되는지 확인했다. 완료 후 후속 수정, `High → Default → Low → None` 전환, 지원하지 않는 값의 명시적인 거부를 검사했다.
- 별도 DB·홈·설정으로 격리한 로컬·외부 클라이언트 프리셋에서 각각11개 생성 요청, 총22개 실제 Strata 생성을 통과했다. 계산 문제의 정답과 후속 변경 정답을 확인하고, 외부로 전달되는 JSON의 수준과 SSE의 추론 출력 유무를 대조했다. 도구와 파일 변경은 비활성화했다.
- 시험용 모델 body에 기본 `reasoning_effort:high`를 둔 상태에서도 None·Low·Medium 선택이 이를 정상 덮어썼다. Default는 이 시험용 기본값을 상속했다. 실제 사용자의 기본 추론 수준은 변경하지 않았다.
- 로컬 생성 `live-local-a`는 모델의 출력 limit을2048로 설정했지만 실제 전송의 출력 상한은 검사하지 않았다. 최종 시험 도구는 body에 `max_tokens:2048`을 명시하고 전송값을 검사하도록 보완했다. 외부 프리셋의 `live-remote-b`는 이 검사까지 포함해11회 모두 통과했다. 이 변경은 시험 도구에만 적용했다.
- 최종 스크립트 모델 검사도 로컬·외부 프리셋 각각11회 통과했다. 이는 선택·전송 계약 검사이며 실제 추론 근거는 위 실제 생성22회와 구분한다. 초기 `mock-local-a`, `mock-remote-a` 결과도 보존했다.
- Python48개 검사를 통과했다. 로컬 설정, 외부 클라이언트 설치, 추론 수준을 프롬프트 뒤에 두는 처리, 수준 변경 시 대화 캐시 재사용 계약과 서버 기본값 우선순위를 포함한다.

```powershell
$env:PYTHONPATH='tools'
python -X utf8 -m unittest tools.test_iq4xs_opencode_setup tools.test_remote_agent_client tools.test_effort_end_args serve.test_server.EffortAtTheEnd serve.test_server.ConfigReasoningEffort
```

재현용 `tools/test_reasoning_selection_runtime.py`는 기본적으로 스크립트 모델을 사용한다. 기존 서버의 실제 생성은 `--live-strata-config <설정 JSON>`을 명시한 경우만 수행한다. API 키나 인증 헤더는 기록하지 않으며 서버가 사용 중이면 새 요청을 제출하지 않는다.

이번 시험은 Rider 화면의 선택 메뉴를 마우스로 누른 검사가 아니라 Rider가 사용하는 ACP 경로 검사다. 짧은 계산·후속 요청으로 선택 적용을 확인했으며 대규모 코딩 품질, 각 수준의 우열, 장기262K 작업 성능을 측정한 결과는 아니다. None·Low·Medium·High별 지연을 캐시 조건이 다른 이 시험에서 성능 순위로 해석하지 않았다.

설치본·일반/개인 배포 ZIP의 동기화, 추론 선택 목록 이외의 전역 설정·Rider ACP·개인 프로필 보존, 최종 서버 유휴 상태는 진단 폴더의 `final-verification.json`에 기록한다. 클라이언트 설치 revision20은 유지한다. Strata 재시작은 필요하지 않다. 실행 중인 OpenCode 연결이 이전 목록을 표시하면 연결을 다시 시작해 갱신한다. 서버 API의 `xhigh` 별칭은 기존 클라이언트 호환성을 위해 유지하며 중복 선택 항목만 제거했다.
