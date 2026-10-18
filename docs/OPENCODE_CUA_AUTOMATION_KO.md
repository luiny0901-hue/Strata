# OpenCode CUA Driver 자동 GUI 작업

이 설정은 OpenCode가 Rider, 브라우저, 설치·설정 창처럼 실제 GUI 화면과 입력이 필요한 작업에서 `cua-driver`를 사용하도록 합니다. CUA Driver가 설치되어 있어야 하며, 이 도구는 드라이버나 모델을 설치하지 않습니다.

## 권한 경계

- 에이전트는 GUI가 필요한 작업에서 CUA Driver를 자동으로 선택합니다.
- 모든 조작은 먼저 대상 프로세스 PID와 정확한 창 ID를 확인하고, 해당 창만 대상으로 합니다.
- 입력은 `background` 방식부터 시도합니다. 드라이버가 `background_unavailable`을 반환하거나, 입력 후 새 화면을 확인해 동작이 실행되지 않았음이 명백할 때만 동일한 동작을 해당 창에 한 번 `foreground`로 재시도할 수 있습니다.
- `foreground`는 잠시 대상 창을 활성화해 실제 키보드·마우스 입력을 전달합니다. 사용자가 입력 중이거나 대상 창이 바뀌었을 가능성이 있으면 실행하지 않습니다.
- 데스크톱 전체 대상 입력은 계속 차단합니다. 권한 거부, 창 식별 실패, 결과 불명확 상태에서는 입력을 반복하거나 셸·네이티브 입력으로 우회하지 않고 멈춥니다.
- UAC 보안 데스크톱은 CUA의 정확한 창 대상이 아니므로 승인할 수 없습니다. UAC가 나타나거나 관리자 권한이 필요하면 `BLOCKED_UAC`와 필요한 사용자 조치를 보고하고 현재 작업을 끝냅니다. 대기·폴링·재시도·권한 우회는 하지 않습니다.
- 각 입력 후 새 화면 상태로 결과를 확인합니다. 효과가 확인되지 않으면 성공으로 보고하지 않습니다.
- 드라이버 권한 모드는 `standard`를 유지합니다. `unrestricted` 또는 승인 우회 모드는 설정하지 않습니다.

## 응답 속도

- 작업 시작 때 `list_windows`로 앱과 PID/HWND를 한 번 식별하고 같은 창을 다루는 동안 재사용합니다. 앱 재시작, 새 창 생성, ID 오류·불일치가 생긴 경우에만 목록을 다시 읽습니다.
- 표준 버튼·입력칸은 좌표 클릭보다 `get_window_state`에서 얻은 `element_token`을 우선 사용합니다. 좌표는 캔버스, 영상, WebGL처럼 접근성 요소가 없는 표면에서만 사용합니다.
- `get_window_state`의 기본 응답은 트리와 스크린샷을 함께 반환합니다. 첫 화면 확인에는 기본 응답을 쓰고, 이후 같은 창의 접근성 상태 갱신에는 직전 `snapshot_id`를 `since`로 전달하고 `include_screenshot:false`를 지정해 변경된 트리만 받습니다. 새 snapshot의 토큰으로 다음 입력을 표적화합니다.
- 화면의 픽셀 자체가 바뀌었는지 판단해야 하거나 접근성 트리에 없는 표면을 조작할 때만 스크린샷을 다시 요청합니다. 기본 `tree_format:"markdown"`을 유지하고, `both`·`full_output` 전체 응답은 필요한 경우에만 요청합니다.
- 큰 창 트리는 이름이 알려진 요소의 `query`, `max_depth`, `max_elements`로 범위를 줄입니다. 트리가 잘렸거나 상태가 모호하면 범위를 넓히거나 화면을 확인하고, 추측으로 입력하지 않습니다.

## 설치 및 적용

저장소 루트에서 실행합니다.

~~~powershell
& "$env:USERPROFILE\Strata\.venv\Scripts\python.exe" tools\configure_opencode_cua_automation.py
~~~

해당 Python 환경을 사용하지 않으면 Python 3.10 이상으로 `py -3 tools\configure_opencode_cua_automation.py`를 실행합니다. macOS/Linux에서는 `python3 tools/configure_opencode_cua_automation.py`를 사용합니다. 다른 OpenCode 설정 파일, Node.js 또는 CUA Driver 경로에는 각각 `--config`, `--node`, `--driver`를 지정할 수 있습니다.

설치기는 기존 설정을 백업하고, 현재 제공자·모델·자격 증명을 보존한 채 CUA 중계기와 창 단위 정책을 설정합니다. 잘못된 JSON이나 예상하지 못한 기존 지침 블록은 덮어쓰지 않고 중단합니다. OpenCode/Rider에서 실행 중인 세션은 설정을 다시 읽도록 안전한 시점에 새 세션으로 시작해야 합니다.

## 확인

- `opencode mcp list`에서 `cua-driver connected`를 확인합니다.
- Rider OpenCode 세션에서 GUI 화면 확인을 요청해 실제 `cua-driver_*` 도구 호출이 나타나는지 확인합니다.
- 실제 입력이 필요한 경우 드라이버의 background 결과를 먼저 읽고, 필요할 때만 정확한 같은 창에 한 번 foreground 입력을 시도합니다.

속도 비교 시에는 같은 앱·창·동작을 기준으로 `list_windows` 횟수, 스크린샷 포함 상태 읽기 횟수, `since` 트리 갱신 횟수와 전체 완료 시간을 기록합니다. 설정 변경만으로 성능 향상을 확정하지 않습니다.

이전 사용자 보고에서 Windows Rider의 창 열기·닫기가 확인됐습니다. 이번 변경에서는 Rider/Hermes 및 GUI 입력을 검증하지 않았습니다. macOS/Linux용 설정은 경로 인자를 받을 수 있지만 해당 플랫폼의 실행 검증은 별도로 해야 합니다.

설치 설명인 이 문서 대신 `examples/opencode/OPENCODE_CUA_AUTOMATION_KO.md`의 짧은 작업 지침을 모델에 전달합니다. 사용자 지정 config에는 지침을 그 config 옆에 설치합니다. 현재 CUA 설치기의 `~/.cua-driver/packages/current` 경로를 탐색하며 명시한 실행 파일이 없으면 다른 버전으로 대체하지 않습니다.
