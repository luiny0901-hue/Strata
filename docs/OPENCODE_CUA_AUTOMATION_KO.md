# OpenCode CUA Driver 자동 GUI 작업

이 설정은 OpenCode가 Rider, 브라우저, 설치·설정 창처럼 실제 GUI 화면과 입력이 필요한 작업에서 `cua-driver`를 사용하도록 합니다. CUA Driver가 설치되어 있어야 하며, 이 도구는 드라이버나 모델을 설치하지 않습니다.

## 권한 경계

- 에이전트는 GUI가 필요한 작업에서 CUA Driver를 자동으로 선택합니다.
- 모든 조작은 먼저 대상 프로세스 PID와 정확한 창 ID를 확인하고, 해당 창만 대상으로 합니다.
- 입력은 `background` 방식부터 시도합니다. 드라이버가 `background_unavailable`을 반환하거나, 입력 후 새 화면을 확인해 동작이 실행되지 않았음이 명백할 때만 동일한 동작을 해당 창에 한 번 `foreground`로 재시도할 수 있습니다.
- `foreground`는 잠시 대상 창을 활성화해 실제 키보드·마우스 입력을 전달합니다. 사용자가 입력 중이거나 대상 창이 바뀌었을 가능성이 있으면 실행하지 않습니다.
- 데스크톱 전체 대상 입력은 계속 차단합니다. 권한 거부, 창 식별 실패, 결과 불명확 상태에서는 입력을 반복하거나 셸·네이티브 입력으로 우회하지 않고 멈춥니다.
- 각 입력 후 새 화면 상태로 결과를 확인합니다. 효과가 확인되지 않으면 성공으로 보고하지 않습니다.
- 드라이버 권한 모드는 `standard`를 유지합니다. `unrestricted` 또는 승인 우회 모드는 설정하지 않습니다.

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

Windows에서 실행 경로와 화면 입력을 확인했습니다. macOS/Linux용 설정은 경로 인자를 받을 수 있지만 해당 플랫폼의 실행 검증은 별도로 해야 합니다.
