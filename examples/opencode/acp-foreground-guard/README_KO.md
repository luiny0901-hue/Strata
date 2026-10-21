# Rider ACP 백그라운드 완료 유실 방지

OpenCode 2.0.22의 ACP는 첫 응답 종료 시 열린 자식 세션이 없으면 이벤트 구독을 닫습니다. 이후 백그라운드 shell 완료가 세션을 재개해도 Rider로 후속 보고가 전달되지 않을 수 있습니다.

이 플러그인은 `OPENCODE_ACP_FOREGROUND_GUARD=1`인 프로세스에서 `shell(background=true)`를 실행 전에 차단하고, 실행되지 않았다는 결과를 모델에 반환합니다. 유한 검증은 충분한 timeout을 지정한 전경 호출로 다시 실행하게 합니다. 일반 전경 호출과 환경변수가 없는 CLI는 그대로 통과합니다. 무한 서비스 명령을 임의로 전경으로 전환하지 않습니다.

설치: 저장소에서 `python tools/configure_acp_foreground_guard.py` 실행 후 Rider의 ACP 연결을 다시 시작합니다. 설치기는 기존 설정과 다른 연결을 보존하고 변경 전 백업을 만듭니다. 다른 설치 위치는 `--config`, `--acp`로 지정합니다. OpenCode v2 전용이며, 기존 OpenCode ACP 항목이 있어야 합니다.

이는 문제를 유발한 호출을 차단하는 실행 보호 장치입니다. OpenCode 바이너리의 일반적인 백그라운드 구독 문제를 수정한 것은 아닙니다. 이미 시작한 백그라운드 작업, 수동 background 전환, 다른 종류의 비동기 작업까지 복구하지 않습니다.

## 2026-10-21 확인

- 설치된 OpenCode 2.0.22 ACP + 로컬 모의 모델: 차단 대상 파일 미생성, 차단 결과 모델 전달, 후속 전경 shell 출력 및 최종 응답이 end_turn 전에 도착함을 확인.
- Node 단위 확인: 활성/비활성 및 전경 호출 통과.
- 기존 session recovery 단위 테스트: 11개 통과.
- 실제 Rider 화면과 Strata 모델을 통한 회귀 실행은 하지 않음. 기존 사용자 세션은 종료하지 않음.
- 시도 이력: 테스트 스크립트 최초 문법 오류 수정. 첫 런타임 시도는 제목 생성 요청을 작업 요청으로 세어 검증 실패. 제목 요청을 분리한 두 번째 시도 통과. 실패 기록은 diagnostics/acp-guard-attempt1에 보존, 통과 기록은 diagnostics/acp-guard-attempt2에 보존.

검증 명령: `node tools/test_acp_foreground_guard.mjs`. 실제 설치 바이너리 검증은 `python tools/test_acp_foreground_runtime.py --binary <opencode.exe> --output <새 진단 디렉터리>`이며 별도 DB와 로컬 모의 모델을 사용합니다.
