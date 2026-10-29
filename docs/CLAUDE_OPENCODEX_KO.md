# Strata + OpenCodex + Claude Desktop Code

이 PC는 다음 연결을 공통으로 사용합니다.

```text
Claude Desktop Code (주 작업면) → OpenCodex 127.0.0.1:10100 → Strata 8080 (기본 모델)
Claude Code CLI (필요할 때)       → OpenCodex 127.0.0.1:10100 → Strata 8080
```

Claude Code 기본 모델은 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`입니다. 실제 추론은 로컬 Strata 모델이 수행합니다. Desktop 3p의 기존 공급자 목록과 Strata 기본 선택은 그대로 사용합니다.

## 사용

로그인 후 기존 시작 프로그램이 Strata를, `opencodex-proxy` 예약 작업이 OpenCodex를 실행합니다. 이미 서버가 실행 중이면 새 서버를 띄울 필요가 없습니다.

주 작업 화면은 **Claude Desktop의 Code**입니다. Claude Desktop에서 **Code → 새로 만들기 → 로컬 폴더 선택**으로 작업 폴더를 열고, 처음 여는 폴더는 신뢰 확인을 마친 뒤 새 Code 세션을 시작합니다. 모델 선택기에서 `Strata (OpenCodex)`를 선택합니다. 이 연결은 Desktop의 기존 3p 게이트웨이 프로필을 사용하며, 한국어·지침·훅·사용자 MCP는 Claude 공통 설정에서 읽습니다. 새 작업을 보내기 전에 Code 하단의 권한 모드 선택기도 확인합니다. 현재 세션이 `수동`이면 도구 사용·명령 실행 권한을 물을 수 있습니다. 설정 재적용은 이미 열린 세션의 모드나 MCP 승인창을 소급 변경하지 않습니다. MCP의 최초 허용 확인은 작업공간 신뢰와 별개입니다.

`run-claude-opencodex.bat`와 `run-claude-opencodex.sh`는 선택형 **터미널 CLI** 실행기이며 Claude Desktop Code 화면을 열지 않습니다. Desktop Code는 앱에서 폴더와 세션을 직접 선택해 시작합니다. Code의 MCP 연결은 Claude Desktop의 일반 채팅 앱 설정인 `claude_desktop_config.json`과 별개로, `~/.claude.json`의 사용자 범위 및 프로젝트 전용(local scope) MCP를 사용합니다.

설정 재적용은 Windows에서 `setup-claude-opencodex.bat`, macOS/Linux에서 `bash setup-claude-opencodex.sh`를 실행합니다. Strata 모델 선택은 OpenCodex 설정에서 읽고, CUA·REA·유지보수 MCP의 정본은 Claude 소유 파일 `~/.claude/strata-mcp.json`에서 읽습니다. 다른 PC에서 Claude 형식 MCP 파일을 가져오려면 `--mcp-config "Claude MCP 파일 경로"`를 지정합니다. 설정기는 저장소의 CUA MCP·정책 및 REA 실행기 경로를 현재 체크아웃으로 바꿉니다. Node.js·CUA Driver·REA 런타임은 해당 PC에서 준비되어 있어야 합니다. 프록시나 모델 조회 실패 시 다른 공급자로 임의 전환하지 않습니다. Windows 실행기는 명시된 `STRATA_CLAUDE_PYTHON`, 저장소 Python 환경, `%USERPROFILE%\Strata\.venv`, 시스템 Python 순서로 찾습니다. 설정기는 이전 프로필에서 쓰던 Python 경로가 여전히 존재하면 `py -3`처럼 다른 인터프리터로 호출해도 기존 경로를 유지합니다. 새 PC이거나 저장 경로가 사라진 경우에는 설정기를 실행한 Python을 사용합니다. 실행기를 바꾸려면 `STRATA_CLAUDE_PYTHON`을 명시하고, 그 값이 유효하지 않으면 프로필을 덮어쓰지 않고 오류를 냅니다.

### CUA·REA 도구를 필요할 때만 불러오기

기본 설정은 CUA와 REA 전체 스키마를 미리 올리지 않는 on-demand 방식입니다. `setup-claude-opencodex.bat` 또는 `bash setup-claude-opencodex.sh`를 실행하면 `agent-tools` 검색·호출 도구 두 개만 등록합니다. 모델이 `search_tools`에서 `cua-driver` 또는 `rea`와 구체적인 검색어를 선택해야 해당 서버가 시작되고, 검색 결과에 포함된 정확한 도구만 `call_tool`로 실행할 수 있습니다. CUA는 실제 GUI 작업에, REA는 기존 바이너리·프로그램 역분석에 사용하고 일반 소스 분석은 Claude의 파일 도구를 사용합니다. CUA/REA 실행 결과의 이미지·구조화 데이터는 원본 MCP 응답 그대로 전달합니다. 이전처럼 전체 도구를 직접 등록하려면 `--direct-cua-rea`를 명시합니다.

이 모드는 `~/.claude.json`의 관리된 CUA/REA 항목만 교체하며 다른 MCP는 보존합니다. Strata 유지보수 연결은 이 저장소 프로젝트의 local scope에만 등록합니다. 변경 전 설정 백업과 영수증을 자동으로 남깁니다. 직접 연결 방식으로 전환하려면 `--direct-cua-rea`를 사용합니다. 현재 진행 중인 Claude 세션에는 적용되지 않으므로 새 Code 세션에서 `/mcp`와 `/context`를 확인합니다. 도구 실행 취소가 들어오면 자식 MCP에도 취소를 전달하지만 작업이 이미 끝났는지 보장할 수 없으므로 결과가 모호하면 상태를 확인하기 전 재실행하지 않습니다.

기본 설정은 읽기 전용 `mcp__agent-tools__search_tools`를 허용해 on-demand 도구 검색의 반복 확인을 줄입니다. Claude 소유 MCP 파일에 실제 `strata-maintenance` 연결이 준비된 경우에는 `environment_status`, `opencodex_service_status`, `restart_status`만 각각 허용해 환경 확인의 반복 확인도 줄입니다. 이 세 권한은 생성된 Claude 공통 설정에서 관리하며, 유지보수 MCP가 더 이상 구성되지 않으면 설정기가 자신이 추가했던 규칙만 제거합니다. 사용자가 소유한 기존 규칙은 보존합니다. CUA/REA 실행 도구 `mcp__agent-tools__call_tool` 및 상태를 바꾸는 `restart_strata`, `cancel_restart`에 대해서는 설정기가 개별 `allow` 규칙을 추가하지 않습니다. 실제 실행 승인은 Claude Code 세션 모드, 프로젝트별 설정, Desktop 앱 확인의 영향을 별도로 받으므로 새 세션에서 확인해야 합니다. `--direct-cua-rea`에서는 검색 규칙을 추가하지 않지만, 유지보수 서버가 있으면 위의 읽기 전용 유지보수 규칙은 그대로 적용합니다.

### 유지보수 MCP를 사용할 때

`strata-maintenance`는 설정기를 실행한 Strata 저장소 폴더에서만 불러옵니다. 일반 앱·게임 프로젝트와 앞으로 여는 새 프로젝트에는 이 서버를 등록하지 않습니다. 유지보수할 때는 Claude Desktop Code에서 해당 Strata 저장소를 작업 폴더로 열고 새 세션을 시작합니다. 그 프로젝트에서도 필요 없으면 `/mcp`에서 끄고, 다음 유지보수 때 다시 켭니다. 이 선택은 프로젝트별로 기억되며 설정 재적용도 사용자가 끈 상태를 보존합니다. 연결된 Git worktree에서는 현재 Claude Code가 사용하는 원본 저장소 경로의 프로젝트 설정을 공유합니다.

설정기는 이전에 관리하던 사용자 전체 범위의 유지보수 연결을 프로젝트 전용으로 옮깁니다. CUA·REA의 on-demand 연결과 다른 사용자 MCP는 보존합니다. 설정 변경은 새 Code 세션에서 확인하고, 이미 진행 중인 작업 때문에 Strata·OpenCodex·Desktop을 재시작하지 않습니다. `doctor.mcp_delivery.maintenance`에서 등록 범위, 프로젝트 경로, 프로젝트 내 활성화 여부와 전체 프로젝트 등록 여부를 확인할 수 있습니다. 이 값은 저장된 설정 검사이며 현재 열린 화면의 연결 상태를 증명하지 않습니다.

## Codex와 다른 클라이언트도 사용할 때

Claude 설정을 마친 뒤 `setup-claude-opencodex.bat clients`(Linux/macOS: `./setup-claude-opencodex.sh clients`)로 Strata 모델 정보·Codex 지연 MCP·공통 지침을 연결합니다. `clients --check`는 저장된 설정 차이만 읽습니다. 모델 API 정보와 각 앱의 압축·권한·MCP는 적용 범위가 다릅니다. [공통 설정과 실제 확인 범위](STRATA_CLIENT_SETTINGS_20261028_KO.md)를 따르세요.

## 새 PC·재설치·외부 PC

### 구성과 확인 범위

| 역할 | 준비 경로 | 이번 확인 범위 |
| --- | --- | --- |
| Windows GPU 서버 | 기존 ON/OFF BAT·관리 실행기와 동일 포크/모델/Pack | 기존 실행 경로 확인, 재설치·GPU 재실행 미검증 |
| Linux GPU 서버 | `SETUP-LINUX-SERVER.sh`와 ON/OFF `.sh` | 프로필·누락 파일 차단·준비 셸의 오프라인 검사, 실제 Linux 엔진 미검증 |
| Windows 접속 PC | 로컬 OpenCodex + Claude Desktop Code + 로컬 MCP | 경로 이전·설정 생성·보존 검사, 새 PC 설치 미검증 |
| Apple Silicon Mac 접속 PC | 로컬 OpenCodex + Claude Desktop Code + 로컬 MCP | Mac 경로·이전 규칙의 모의 검사, 실제 Mac 앱·CUA·접속 미검증 |

접속 PC는 서버와 같은 OS일 필요가 없습니다. 프로젝트 파일과 GUI는 접속 PC에서 다루고 모델 요청만 서버로 보냅니다. 서버 프로젝트 파일까지 자동 복제·동기화하거나 서버 화면을 자동으로 원격 조작하는 구성은 아닙니다.

### 통합 설치로 준비하기

새 PC·재설치는 Windows `INSTALL-STRATA-AGENT.bat`, Mac `bash install-strata-agent.sh`, Linux 서버 `bash install-strata-agent.sh --role server`로 시작합니다. Python이 없는 단계부터 필요한 클라이언트 프로그램 설치와 기존 설정기 적용까지 이어갑니다. [통합 설치 안내](INTEGRATED_INSTALL_KO.md)에 포함 항목·권한/복원 대기·재개 방법과 검증 범위를 정리했습니다.

아래는 직접 구성하거나 기존 환경의 설정만 다시 적용할 때 쓰는 수동 절차입니다.

### 처음 한 번 준비

1. 서버에는 기존 실행기·정확히 같은 포크 엔진·모델·Pack을 복원합니다. 접속 PC에는 [Claude Desktop](https://claude.com/download), Python 3.10 이상, Node.js LTS와 CUA Driver를 설치합니다. 서버만 운영하는 Linux에는 GUI용 CUA를 설치하지 않습니다.
2. OpenCodex는 자체 [설치 안내](https://opencodex.me/getting-started/installation/)를 사용합니다. CLI 방식은 `npm install -g @bitkyc08/opencodex`이며 Node.js가 필요합니다. OpenCodex의 기존 서비스·GUI를 사용하고 이 저장소에서 다른 프록시나 서비스 관리자를 만들지 않습니다.
3. 접속 PC의 OpenCodex에서 **이름이 `strata`인 공급자**를 설정합니다. 주소는 같은 PC면 `http://127.0.0.1:8080/v1`, 아래 터널이면 `http://127.0.0.1:18080/v1`입니다. 모델 ID는 서버가 실제 제공하는 ID를 고르고, API 키는 해당 서버의 키를 입력합니다. 모델·컨텍스트 조회로 준비 여부를 확인합니다.
4. OpenCodex의 Claude Desktop 게이트웨이를 적용합니다. 설치된 OpenCodex의 `ocx claude desktop apply --gateway` 또는 같은 기능의 GUI를 사용합니다. Desktop은 **접속 PC의** OpenCodex `http://127.0.0.1:10100`으로 연결합니다. 서버의 10100 주소나 Strata 8080을 Desktop 게이트웨이에 혼용하지 않습니다.
5. Windows는 `setup-claude-opencodex.bat`, Mac은 `bash setup-claude-opencodex.sh`를 실행합니다. 새 PC는 CUA·REA 기본 MCP 연결을 자동 생성합니다. 사용자 지정 MCP가 필요할 때만 `--mcp-config`를 추가합니다. Windows에서 `python`이 없고 `py -3`만 있어도 실행기를 사용할 수 있습니다. 명시한 Python이나 CUA 경로가 잘못되면 다른 실행 파일로 몰래 바꾸지 않습니다.
도구 지연 검색은 적용된 Desktop 프로필의 `toolSearchEnabled: true`와 새 세션의 실제 검색·호출로 확인합니다. CLI의 `ENABLE_TOOL_SEARCH`만으로 Desktop 연결을 증명하지 않습니다.

6. `doctor`로 공통 연결과 `desktop_ready`를 구분해 확인하고, Claude Desktop Code의 새 세션에서 Strata 모델·262.1k·MCP를 확인합니다. 등록·저장 진단은 실제 도구 호출 성공이나 OS 권한 승인을 대신하지 않습니다.

Mac에서 `.command`를 사용하려면 처음 한 번 `chmod +x setup-claude-opencodex.command` 후 실행할 수 있습니다. OS가 신뢰 확인을 요구하면 사람이 확인합니다. CUA의 [설치·권한 안내](https://cua.ai/docs/cua-driver/quickstart)에 따라 접근성·화면 기록을 허용해야 합니다. 기본 설치가 PATH에 없으면 `STRATA_CUA_DRIVER_EXE`에 이 Mac의 실행 파일 경로를 지정합니다. Windows `.exe` 경로는 사용하지 않습니다.

### 외부 서버 연결

현재 유지보수 진단은 로컬 Strata 주소만 사용합니다. 외부 PC에서는 **접속 PC에 OpenCodex를 두고 SSH로 서버의 8080을 로컬 18080에 연결**하면 이 경로를 그대로 사용할 수 있습니다.

서버의 SSH 로그인이 먼저 준비되어 있어야 합니다. Windows는 [Microsoft OpenSSH 설치 안내](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)를, Linux는 해당 배포판의 OpenSSH 서버 설치 절차를 따릅니다. 외부 네트워크에서는 사설 VPN 등으로 서버 SSH 주소에 도달할 수 있어야 합니다. 이 설정기는 SSH 서버·VPN·방화벽·공유기를 자동 변경하지 않습니다.

Windows 터미널 또는 Mac 터미널에서 실행하고 창을 유지합니다. `사용자@서버주소`를 실제 SSH 계정과 도달 가능한 서버 주소로 바꾸세요.

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:18080:127.0.0.1:8080 사용자@서버주소
```

이때 서버 Strata는 `127.0.0.1:8080`에서 실행해도 됩니다. 접속 PC OpenCodex 공급자 주소를 `http://127.0.0.1:18080/v1`로 맞추고 서버의 API 키를 사용합니다. 서버나 프록시의 포트를 인터넷에 직접 공개할 필요가 없습니다. [SSH 포트 전달의 동작](https://man.openbsd.org/ssh.1)을 참고하세요.

터널의 로컬 포트가 이미 사용 중이면 위 명령은 실패하며 기존 프로세스를 종료하지 않습니다. 터널 또는 네트워크가 끊기면 요청 실패를 확인하고 복구 후 새 요청을 보냅니다. 연결이 끊긴 작업을 처음부터 자동 재실행하거나 SSH 호스트 키·로그인 확인을 우회하지 않습니다. CUA는 접속 PC의 화면을 조작하며 서버 화면을 조작하지 않습니다. 실행 환경 유지보수와 재시작은 대상 서버에서 별도로 수행합니다.

### 다시 설치할 때

서버의 모델·Pack·포크 버전·ON/OFF 설정·API 키와 프로젝트 소스/데이터를 별도 보관하세요. 클라이언트에서는 기존 OpenCodex 공급자/게이트웨이 설정과 사용자 지정 MCP·검색 키·지침을 필요한 범위로 백업하고, 다른 사람이나 공개 저장소에 비밀 값을 넣지 않습니다. OS별 앱 설치와 키체인/OS 권한은 새 PC에서 다시 확인합니다.

프로젝트를 복원한 뒤 위 준비 절차를 다시 실행합니다. 다른 OS의 `.venv`, 설치 경로가 든 Claude 전체 설정, 사용자 SID·예약 작업·Desktop 재시작 소유 정보는 그대로 복사하지 않습니다. 설정기는 자체 변경 전 백업과 영수증을 남기고 다른 설정·사용자 지침은 보존합니다. 수동 수정한 생성 지침이 있으면 이를 검토해 병합하며 보호 해시를 임의로 재설정하지 않습니다.

### 준비 상태 진단

외부 PC와 새 설치에서 실제 앱 프로필이 준비됐는지는 `doctor`의 `desktop_ready` 필드를 확인합니다. `ready`는 공통 연결 경로의 검사이고, `desktop_ready`는 Claude Desktop 3p 게이트웨이까지 확인한 결과입니다. 지연 MCP 사용 시 `checks.managed_mcp_permission_configuration`과 `mcp_permissions.status`는 저장된 서버별 허용 규칙 및 그보다 우선하는 `ask`·`deny` 규칙을 점검합니다. `desktop_permission_mode.default_mode`와 `checks.desktop_permission_mode_configuration`은 저장된 새 세션 기본 권한 모드만 진단하며, 폴더별 선택이나 현재 세션 모드·Desktop 승인창은 확인하지 않습니다. MCP와 권한 모드의 `runtime_status`는 실제 새 세션에서 확인하기 전까지 `not_verified`입니다. `desktop.status`가 `not_configured`, `profile_mismatch`, `invalid_profile`이면 Desktop 앱의 게이트웨이 프로필을 먼저 설정하세요. `CLAUDE_3P_CONFIG_LIBRARY` 환경 변수로 기본 위치가 다른 설치를 지정할 수 있습니다. Mac 기본 경로는 `~/Library/Application Support/Claude-3p/configLibrary`이며 OpenCodex의 `OPENCODEX_CLAUDE_DESKTOP_CONFIG_DIR`와 Desktop의 `CLAUDE_USER_DATA_DIR` 지정도 진단에 반영합니다.

저장소 폴더에서 다음 명령으로 읽기 전용 진단을 실행합니다. Windows에서는 `setup-claude-opencodex.bat doctor`, macOS/Linux에서는 `bash setup-claude-opencodex.sh doctor`를 사용해도 됩니다.

```powershell
python .\tools\claude_opencodex_client.py doctor
```

macOS/Linux에서는 `python3 tools/claude_opencodex_client.py doctor`를 사용합니다.

`doctor`와 Claude Code의 `environment_status`는 준비 상태, 물리 메모리 여유량의 순간 관측, 도구·추론·캐시 기능에 대한 읽기 전용 Messages 경로 미리보기, 최근 Claude Messages 실제 경로 기록을 표시합니다. 물리 메모리 값은 GPU 메모리와 작업별 추가 요구량을 포함하지 않으므로 대용량 작업이 들어간다는 보장은 아닙니다. `environment_status`에는 Strata `/slots`와 OpenCodex의 `/api/provider-request-pacing?name=strata` 상태도 있습니다. OpenCodex 페이싱 상태는 해당 큐가 추적하는 요청만 보여줍니다. 페이싱이 꺼져 있으면 `not_tracking`이며 `queued: 0`을 전체 유휴로 해석할 수 없습니다. `in_flight`도 페이싱 설정에 따라 생략될 수 있습니다. Strata `idle` 역시 실행 슬롯만 비었다는 뜻이므로, 둘 중 어느 상태도 프록시 전체 유휴 증거로 단독 사용하지 않습니다. 실제 기록은 최근 Strata 요청 최대 12건에서 CLI(`claude`)와 Desktop(`claude-desktop`) 표본을 분리해 건수·중앙 지연·첫 출력 지연을 계산합니다. 프롬프트·응답·헤더·요청 ID는 출력하지 않습니다. 이 작은 최근 표본은 벤치마크가 아니며 검색·이미지·정책별 경로를 대신하지 않습니다. 관리 토큰이 없으면 연결 진단은 계속되고 경로 정보만 `unavailable`로 표시됩니다.

`strata-maintenance.environment_status`에는 추가 요청 로그 표본을 켜는 선택 인자도 있습니다. 기본 호출은 요청 로그 CLI를 실행하지 않습니다. 필요할 때 `include_opencodex_requests=true`와 `request_window=15m|1h`를 지정하면 기록된 OpenCodex 소유자의 Bun/CLI로 Claude 묶음 로그를 한 번 읽습니다. 최대 12건, 8초, stdout 128 KiB로 제한하고 시간·상태·effort·토큰 사용량만 허용 목록으로 반환합니다. CLI와 Desktop은 구분되지 않으므로 UI 시각과 직접 맞춰야 합니다. `close_reason=terminal`은 body EOF일 뿐 Anthropic `message_stop` 또는 Desktop 완료의 증거가 아닙니다.

## 컨텍스트 창

Strata 모델 한도와 Claude의 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `autoCompactWindow`는 262,144에 맞춥니다. 이전 설정기의 196,608 고정 상한은 제거했습니다. 응답 상한은 32,000이며 Claude의 기본 압축·응답 버퍼가 창 안에 확보됩니다. 설정 파일 저장과 열린 Desktop 세션의 반영은 구분하며, 새 Code 세션에서 262.1k 표시를 확인합니다.

## 공통 설정

- `~/.claude/settings.json`: CLI의 10100 연결, Strata 기본·보조 모델, 한국어, 추론 선택, 실제 서버 창에 맞춘 문맥·출력 한도, 네이티브 압축, 기존 한국어·엔진·데스크톱 지침 훅. Desktop은 연결 주소·모델·일부 timeout을 자체 설정으로 주입하므로 같은 env 값이라고 가정하지 않습니다.
- `~/.claude/CLAUDE.md`, `~/.claude/guidance/`: 기존 정본에서 생성한 전문 개발·유지보수 지침. 엔진 상세 지침은 관련 프로젝트에만 추가합니다.
- `~/.claude/strata-mcp.json`: Claude 전용 CUA·REA 및 선택적 Strata 유지보수 MCP 정본. `~/.claude.json`의 `agent-tools`는 이 파일을 읽습니다.
- `~/.claude.json`의 `mcpServers`: 사용자 범위의 지연 `agent-tools` 연결. 선택적 `strata-maintenance`는 같은 파일의 `projects[저장소 경로].mcpServers`에만 등록합니다. Desktop 로컬 Code와 CLI에서 별도의 `--mcp-config` 없이 로드합니다. 다른 사용자 MCP와 세션 정보는 보존합니다.
- `~/.claude/strata-opencodex.json`: 이 연결을 사용한다는 표식과 관리 파일 해시. 기존 별도 프로필 `~/.config/strata/claude-code`와 그 대화는 보존합니다.

Claude Code CLI와 Claude Desktop Code는 `~/.claude/settings.json`, `~/.claude.json`, 프로젝트의 `CLAUDE.md`·`.mcp.json`을 공유하므로 MCP 연결과 허용·질문·거부 규칙은 양쪽에 적용됩니다. Desktop Code의 권한 모드는 전송창 아래 선택기에서 바꿀 수 있습니다. `permissions.defaultMode`는 새 로컬 세션의 기본값이고, Desktop에서 폴더별로 선택했던 모드는 그 폴더에서 기본값보다 우선하며 이미 열린 세션은 설정 재적용으로 바뀌지 않습니다. 따라서 저장 설정 진단은 현재 Code 화면의 모드나 대기 중인 승인창을 증명하지 않습니다. `bypassPermissions`는 권한 확인을 건너뛰는 모드이며 관리자 권한/UAC 확인과 Windows 보안 대화상자는 별도입니다. MCP 최초 연결 확인도 폴더 신뢰와 별개입니다.

로컬 프록시에는 OpenCodex가 정의한 공개 표식 `opencodex-proxy`를 사용합니다. Strata 공급자 비밀 키를 공통 설정에 복사하지 않습니다. 실제 인증을 요구하는 프록시로 변경할 때는 해당 프록시가 발급한 클라이언트 자격 증명으로 별도 설정해야 합니다.

설정 변경 전 원본과 새 파일 목록은 `~/.claude/backups/strata-opencodex-<시각>/files.json`에 기록합니다. 현재 영수증은 `files`·`state`·`published`·`rollback_conflicts`를 가진 객체이며 초기 버전 영수증은 파일 목록 배열입니다. 파일을 모두 준비한 뒤 동시 변경을 확인하고 게시하며, 중간 실패 시 아직 이번 적용 내용과 일치하는 파일만 되돌립니다. 충돌한 다른 세션의 변경은 보존하고 영수증에 남깁니다. 수동 수정한 생성 지침이나 충돌하는 사용자 MCP는 덮어쓰지 않고 알려줍니다. 다른 설정·추론 선택·개인 훅은 재적용 때 보존합니다.

실행 환경 자체의 유지보수 절차는 [유지보수 지침](CLAUDE_SELF_MAINTENANCE_KO.md), 이전 점검은 [검증 기록](CLAUDE_SELF_MAINTENANCE_20261025_KO.md), 실제 Claude Desktop Code 세션 검증은 [2026-10-26 검증 기록](CLAUDE_DESKTOP_CODE_20261026_KO.md)을 참고하세요. 일반 프로젝트 작업마다 상세 유지보수 절차를 읽지 않습니다. 유지보수 진단은 불필요한 전체 공급자 모델 목록 갱신 없이 실제 Strata 상태를 확인합니다. 초기 설치/재적용의 모델 탐색은 별도 검사합니다.

## 2026-10-25 검증

- Strata 시작 프로그램 바로가기와 로그인 예약 작업을 확인했습니다. 실제 로그인/재부팅 시험은 하지 않았습니다. 프록시는 단일 인스턴스 실행 정책으로 현재 실행 중이며 `/healthz` 정상, Strata 모델 조회 및 `/v1/messages/count_tokens` 200입니다.
- 실제 Claude Code 네이티브 실행: Read → Write → Read로 `TOTAL=42\n` 저장·확인, 19.622초, 종료 0.
- 같은 대화를 일반 `claude.exe`로 재개: Read → Edit → Read로 `TOTAL=43\n` 수정·확인, 24.099초, 종료 0. 보호한 입력 파일 해시 일치.
- 같은 후속 작업에서 ToolSearch와 CUA `list_windows`, REA `list_cutter_sessions`를 각 1회 실제 호출했습니다. 도구 오류 없이 완료했습니다. REA에는 활성 Cutter 브리지가 없다는 조회 결과이며 실제 역분석 증거는 아닙니다. 사용자 마우스·키보드 입력은 수행하지 않았습니다.
- 두 실행 모두 모델 ID, CUA·REA의 `source:user`, 한국어 완료 보고를 확인했습니다. 초기 SessionStart 훅 성공을 확인했습니다.
- 공통 설정/기존 직결 클라이언트 단위 검사 26개 통과. 공통 설정 재적용은 변경 0개로 확인했습니다.
- 처음 `/health`를 JSON으로 읽은 탐색은 HTML 응답 때문에 실패했습니다. 설치 소스의 정식 `/healthz`로 확인해 수정했습니다. 모델 ID가 공식 Claude 모델명이 아니라는 `unrecognized_model` stderr 경고는 남아 있으며 실제 요청·도구·파일 검증은 성공했습니다.
- OpenCodex 공급자 설정, Desktop 3p 프로필, 기존 Claude 전용 프로필은 전후 파일 해시가 일치합니다.
- 이 설정 점검은 262K 장문 압축, 장시간 무인 실행, 재부팅·외부 PC 접속을 검증한 결과가 아닙니다.

진단 원본: `C:\Users\luiny\Strata-data\diagnostics\claude-opencodex-common-20261025`.

현재는 Strata 공급자를 Anthropic 방식과 OpenCodex의 원본 Messages 옵션으로 연결합니다. 도구 검색 뒤 긴 입력의 캐시 손실을 줄인 결과는 [연결 지연 측정](CLAUDE_OPENCODEX_LATENCY_20261025_KO.md)에 있습니다. 검색·이미지·특정 정책 요청은 기존 변환 경로를 사용할 수 있으며, 모든 작업의 전체 시간이 빨라졌다고 보장하지 않습니다. 과거 직결 경로나 다른 캐시 조건의 성능 수치를 재사용하지 않습니다.

현재 Desktop Code에서 쓰는 사용자 지정 Strata Qwen 모델은 ToolSearch가 실제로 노출되지 않는 것을 새 세션에서 확인했습니다. `ENABLE_TOOL_SEARCH=true`도 기능을 켜지 못했고, 이 모델에서는 전체 MCP 도구 정의가 미리 로드된다고 봐야 합니다. 이전 Claude 모델 시험의 검색 성공이나 캐시 개선을 현재 모델에 그대로 적용하지 마세요. 직접 CUA·REA 등록 시 약 98.5k/318개였던 값은 이전 관측입니다. 일반 프로젝트의 on-demand 사용자 MCP는 `agent-tools` 2개 도구이며, 유지보수 프로젝트에서만 `strata-maintenance` 9개 도구가 추가됩니다. Desktop 내장 도구 비용은 별도로 표시됩니다. 세션마다 `/context`로 실제 목록을 확인합니다. 자세한 최신 결과는 [2026-10-26 검증 기록](CLAUDE_DESKTOP_CODE_20261026_KO.md)을 참고하세요.

설정 범위와 IDE 사용 방식: [Claude Desktop Code](https://code.claude.com/docs/en/desktop), [Claude Code 설정](https://code.claude.com/docs/en/settings), [MCP 연결](https://code.claude.com/docs/en/mcp).


## 2026-10-28 OS 이전·새 PC 경로 점검

새 MCP 소유 파일과 이전 관리 연결이 없는 PC에서는 설치된 Node/npx·CUA와 저장소의 기존 정책/REA 실행기로 기본 연결을 생성한다. 가져온 CUA의 Windows node.exe·드라이버 경로와 REA의 이전 Python 경로는 현재 클라이언트 경로로 재지정한다. 명시한 CUA/Python 실행 파일이 잘못되면 임의 대체하지 않는다. Desktop 진단은 Mac·Linux 경로와 명시한 사용자 데이터 경로를 반영한다. Windows 설정기는 py -3 탐색을 지원하고 내부 탐색값을 사용자 Python 지정값과 구분한다. POSIX 실행기의 CRLF와 명시 Python 무시 문제를 수정했고 Mac .command 진입점을 기존 설정기에 연결했다.

선택한 공통 클라이언트 검사 9개의 첫 실행은 8개 통과, 새 모의 OS 경로 검사 1개가 빈 환경에서 Path.home을 찾지 못해 실패했다. 시험 홈을 명시한 후 해당 검사 1개/0.008초/OK였다. Linux 프로필·부트스트랩과 셸 fixture는 8개/1.121초/OK였다. 이후 REA 명령 재지정 변경에 영향받는 검사 6개/0.550초/OK, 셸 변경 관련 2개/0.421초/OK였다. 중복을 제외하면 관련 검사 18개를 확인했으며 신규 사례는 기존 파일의 5개이고 별도 검사기는 추가하지 않았다.

실행 명령은 `python -B -X utf8 -m unittest tools.test_agent_setup_bootstrap -q`와 기존 `tools.test_claude_opencodex_client.SharedClaudeTests`의 새 PC 생성·CUA 이전·명시 경로·OS별 Desktop 경로·Desktop 준비 진단·REA 이전·기존 Python 보존·설정 보존·MCP 소유 파일 보존·수동 지침 보호 사례를 선택한 unittest 호출이다. 최초 검사와 재실행 출력은 이 작업의 도구 기록에 있다.

Windows 실행기 `cmd.exe /d /c setup-claude-opencodex.bat clients --help`는 종료 0이었다. 새 .command의 `bash -n`은 샌드박스의 MSYS 내부 객체 권한 때문에 첫 실행에 실패했고 허용된 환경에서 같은 문법 검사만 재실행해 종료 0이었다. 안내문서의 로컬 링크와 POSIX 실행기의 LF를 확인했다. 안내 갱신 도구는 첫 시도에 기존 제목 불일치로 게시 전에 중단했으며, 실제 제목을 확인해 수정한 뒤 게시했다.

소스 백업 영수증: `C:/Users/luiny/.claude/backups/strata-opencodex-20261028T144027431577Z/files.json`, `C:/Users/luiny/.claude/backups/strata-opencodex-20261028T144559678702Z/files.json`, `C:/Users/luiny/.claude/backups/strata-opencodex-20261028T144750235854Z/files.json`. 시험 홈 수정은 별도 백업을 남겼다. 실제 사용자 설정·공급자·실행 중 서비스·방화벽·SSH·VPN은 변경하지 않았다. 패키지/모델을 설치하거나 Linux GPU, 실제 Mac, 새로 설치한 PC, 외부 네트워크에서 실행한 결과가 아니다. SSH·Mac 권한 절차는 위 공식 원문을 확인해 안내에 반영했다. 코드 준비·오프라인 검사를 전체 환경의 실기 통과로 표시하지 않는다.
