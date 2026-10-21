# 사용자 포인터를 사용하지 않는 OpenCode CUA 입력

2026-10-21부터 OpenCode 프록시는 모든 입력을 `background`로 제한합니다. 드라이버 v0.36.0의 도구 설명에 따르면 `move_cursor`는 실제 마우스를 움직이지 않는 에이전트 오버레이이며, `foreground` 입력은 Windows SetForegroundWindow/SendInput을 사용합니다. 이전 foreground 재시도 허용 정책을 제거했습니다.

- 프록시: foreground 요청을 거부하고 생략된 입력 모드는 background로 명시합니다.
- launch_app은 포커스 탈취 가능성이 있어 카탈로그와 Rego에서 제외합니다. 별도 셸 실행으로 우회하지 않습니다.
- 새 화면 조회를 시작하면 이전 픽셀 근거를 무효화합니다. 늦게 도착한 이전 조회 결과는 stale_capture로 반환하고 이미지·토큰을 입력 근거로 쓰지 못하게 합니다.
- 드라이버 Rego 정책: background로 명시된 창 입력만 허용합니다.
- 모델 도구 카탈로그: foreground 선택지와 재시도 안내를 제거합니다.
- 한국어 지침: 사용자 마우스, SendInput, 셸/네이티브 입력 우회를 금지합니다.
- background 미지원 또는 무동작이면 `BACKGROUND_ONLY_UNSUPPORTED`로 보고하고 중단합니다. 일부 Rider/Chromium/캔버스 동작은 이 제한에서 수행할 수 없습니다.

적용 명령은 `python tools/configure_opencode_cua_automation.py`입니다. 기존 설정은 백업하고 다른 설정을 보존합니다. 외부 클라이언트 설치도 같은 `prepare_configuration`을 재사용합니다. 적용 후 OpenCode/Rider ACP 연결을 다시 시작해야 합니다. 이미 실행된 MCP 프로세스에는 새 제한이 소급 적용되지 않습니다.

검증: Node 정책·카탈로그 테스트 13개, Python 설정 테스트 11개 통과. `python tools/cua-driver/verify-installed-background-only.py`로 실제 설치된 MCP 프록시의 도구 카탈로그와 9개 foreground 요청의 실행 전 거부를 확인했습니다. 실제 사용자 창에 입력하지 않았으며, 물리 마우스와 동시에 사용하는 GUI 실험은 수행하지 않았습니다.

이 제한은 설정된 CUA MCP 경로를 대상으로 합니다. 별도로 실행한 다른 도구나 드라이버 프로세스까지 운영체제 차원에서 격리하는 기능은 아닙니다.

## 좌표 정확도 보완

2026-10-21 추가: 설치 드라이버의 `move_cursor`는 화면 절대좌표, click/drag는 반환 스크린샷 좌표를 사용합니다. OpenCode 프록시는 두 도구의 사용자 입력 좌표를 반환 PNG 내부 픽셀로 통일하고, overlay 이동에만 창 원점과 실제 PNG/창 크기 비율을 적용합니다. 클릭 좌표에는 별도 배율을 더하지 않습니다. 이미지 응답에는 `CUA_COORDINATES` 안내를 덧붙입니다. 표준 컨트롤은 element_token을 우선합니다.

- 기본 window scope를 생략한 pid/window_id 호출을 정상 허용하며, target과 중복 PID/HWND가 서로 다르면 거부합니다.
- 픽셀 입력은 같은 프록시에서 최근 120초 안에 읽은 해당 창의 PNG가 있어야 합니다. display_only/tree-only 응답은 새 픽셀 근거로 인정하지 않습니다.
- 이미지 밖 좌표, 줌 좌표, 다른 창, 일치하지 않는 capture_id는 native 입력 전에 거부합니다. 드라이버가 capture_id를 제공하고 해당 도구 스키마가 지원하면 자동으로 연결합니다.
- 입력 후 화면 근거를 무효화합니다. 새 화면 확인 없는 반복 클릭과 입력 도중 겹치는 조작을 차단합니다. 읽는 중 입력이 발생했다면 뒤늦게 도착한 이전 화면은 새 근거로 인정하지 않습니다.
- 현재 snapshot의 element_token 입력은 이미지 없이도 가능하며 불필요한 포인터 이동을 요구하지 않습니다. 모델의 화면 판독 자체가 정확한지는 이 검증으로 보장하지 않습니다.

검증: Node 정책/좌표/카탈로그 20개, Python 설치기 11개, 외부 클라이언트 설정 6개 통과. 설치 MCP를 통한 실제 PNG 크기·창 bounds 확인, 스크린샷 없는 클릭 및 이미지 범위 밖 클릭의 실행 전 거부를 확인했습니다. 전경 입력 9종 차단도 유지됩니다. 실제 사용자 창에는 클릭하지 않았습니다. 첫 클릭 성공률을 측정하는 Rider/Chromium GUI 회귀 실험은 수행하지 않았습니다.

재현: `node --test tools/cua-driver/opencode-grounding.test.mjs tools/cua-driver/opencode-policy.test.mjs tools/cua-driver/opencode-catalog.test.mjs` 및 `python tools/cua-driver/verify-installed-background-only.py --coordinates`.
