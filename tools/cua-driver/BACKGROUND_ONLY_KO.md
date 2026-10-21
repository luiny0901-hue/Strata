# 사용자 포인터를 사용하지 않는 OpenCode CUA 입력

2026-10-21부터 OpenCode 프록시는 모든 입력을 `background`로 제한합니다. 드라이버 v0.36.0의 도구 설명에 따르면 `move_cursor`는 실제 마우스를 움직이지 않는 에이전트 오버레이이며, `foreground` 입력은 Windows SetForegroundWindow/SendInput을 사용합니다. 이전 foreground 재시도 허용 정책을 제거했습니다.

- 프록시: foreground 요청을 거부하고 생략된 입력 모드는 background로 명시합니다.
- 드라이버 Rego 정책: background로 명시된 창 입력만 허용합니다.
- 모델 도구 카탈로그: foreground 선택지와 재시도 안내를 제거합니다.
- 한국어 지침: 사용자 마우스, SendInput, 셸/네이티브 입력 우회를 금지합니다.
- background 미지원 또는 무동작이면 `BACKGROUND_ONLY_UNSUPPORTED`로 보고하고 중단합니다. 일부 Rider/Chromium/캔버스 동작은 이 제한에서 수행할 수 없습니다.

적용 명령은 `python tools/configure_opencode_cua_automation.py`입니다. 기존 설정은 백업하고 다른 설정을 보존합니다. 외부 클라이언트 설치도 같은 `prepare_configuration`을 재사용합니다. 적용 후 OpenCode/Rider ACP 연결을 다시 시작해야 합니다. 이미 실행된 MCP 프로세스에는 새 제한이 소급 적용되지 않습니다.

검증: Node 정책·카탈로그 테스트 13개, Python 설정 테스트 11개 통과. `python tools/cua-driver/verify-installed-background-only.py`로 실제 설치된 MCP 프록시의 도구 카탈로그와 9개 foreground 요청의 실행 전 거부를 확인했습니다. 실제 사용자 창에 입력하지 않았으며, 물리 마우스와 동시에 사용하는 GUI 실험은 수행하지 않았습니다.

이 제한은 설정된 CUA MCP 경로를 대상으로 합니다. 별도로 실행한 다른 도구나 드라이버 프로세스까지 운영체제 차원에서 격리하는 기능은 아닙니다.
