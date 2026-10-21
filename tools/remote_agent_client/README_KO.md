# Windows/Mac 원격 Strata 클라이언트 설정

이 도구는 이미 실행 중인 Strata 서버를 Windows 또는 Apple Silicon Mac의 OpenCode와 Rider에 연결합니다. 같은 서버 PC에서도 주소를 127.0.0.1:8080으로 지정해 사용할 수 있습니다. 공식 Cua Driver는 화면을 조작할 클라이언트에 설치하고 OpenCode 로컬 MCP로 등록합니다. Strata, 모델, 방화벽, GPU는 이 클라이언트 도구가 설치하거나 변경하지 않습니다.

## 가장 짧은 사용 흐름

| 작업 | Windows 저장소 루트 | Apple Silicon Mac 저장소 루트 |
|---|---|---|
| 처음 설치·재설정 | `SETUP-OPENCODE.bat setup` | `sh setup-opencode.sh setup` |
| 평소 실행 | `SETUP-OPENCODE.bat run` | `sh setup-opencode.sh run` |
| 접속·설정 진단 | `SETUP-OPENCODE.bat doctor` | `sh setup-opencode.sh doctor` |

`run`은 설치 질문·서버 상태 조회를 반복하지 않고 저장된 wrapper를 실행합니다. `run -- --version`처럼 OpenCode 인자를 전달할 수 있습니다. 설정이 없으면 setup 안내를 표시합니다. 서버가 꺼져 있으면 서버 PC에서 먼저 실행하세요. 원격 GPU 추론과 로컬 CUA/REA는 서로 다른 실행 위치입니다.

## 필요한 것

- Python 3.10+ 및 Node.js
- OpenCode CLI가 설치되어 PATH에서 실행 가능
- Strata 호스트의 신뢰 가능한 LAN 또는 Tailscale 주소와 API 키
- Strata 서버가 시작되어 `/health`와 인증된 `/v1/models`에 응답하는 상태

서버를 인터넷에 포트 포워딩하거나 공개 네트워크에 노출하지 마세요. 직접 연결에는 신뢰 가능한 Private LAN 또는 Tailscale만 사용합니다.

## 설치 및 사용

저장소 루트에서 실행합니다.

```powershell
# Windows PowerShell
.\tools\remote_agent_client\setup-windows.bat setup
```

```sh
# Apple Silicon Mac
sh tools/remote_agent_client/setup-macos.sh setup
```

도구가 서버 주소와 키를 묻습니다. 키는 숨김 입력이며, 먼저 `/health`와 인증된 `/v1/models`를 확인합니다. 모델 ID는 서버 응답에서 선택하므로 프로필 이름을 추측하지 않습니다. 여러 모델이 있으면 목록에서 선택합니다. context와 이미지 capability는 `/health`가 반환한 값만 사용합니다. 이후 CUA Driver가 없으면 공식 설치기를 내려받을지 묻습니다. 기본 응답은 설치이며, `n`을 입력하면 Strata 연결은 계속 설정하고 CUA만 건너뜁니다.

CUA 단계 다음에는 REA 등록 여부를 묻습니다. 현재 버전의 기존 등록과 분석 범위가 일치하면 질문·setup을 반복하지 않고 재사용합니다. 새 등록은 Node.js 22.19+, 24.11+ 또는 26+와 `npx`를 확인한 후 공식 `npx -y rea-agents@6.7.0 setup --yes --client opencode`를 사용합니다. `n`을 입력하거나 REA 등록이 실패해도 Strata 연결은 보존됩니다. 등록 재사용은 실제 MCP 연결·분석 성공 검증이 아닙니다.

설치기는 관리자 권한 없이 실행합니다. Windows에서는 사용자 PATH 변경과 자동 시작 작업을 건너뛰고, macOS에서는 셸 PATH 파일을 변경하지 않습니다. macOS 최초 설치에서는 CuaDriver.app을 시작해 권한 안내를 열 수 있습니다. 화면 기록과 손쉬운 사용 권한은 macOS System Settings에서 직접 승인해야 합니다.

설정이 끝나면 Rider를 재시작하고 AI Chat의 agent 선택기에서 `OpenCode Strata`를 고릅니다. OpenCode 터미널 작업은 다음 wrapper를 사용합니다.

설정 revision 4부터 ACP 완료 이후 숨은 자동 재개 방지와 잘린 도구 호출 복구 플러그인도 함께 설치합니다. CUA 사용 여부와 관계없이 적용되며, 설치 영수증의 파일 해시 검사에 포함됩니다. Rider ACP 항목은 실행 보호 환경변수를 갖고, 일반 터미널 실행에는 ACP 전용 제한을 강제하지 않습니다. CUA를 설치하면 사용자 포인터 대신 background 입력과 최신 스크린샷 좌표 검증을 사용합니다.

revision 5부터 Windows ACP의 실제 PowerShell 호출에도 UTF-8 파일 전달, 오류 종료 코드, 비대화형 입력 및 UAC 요청 사전 검사를 적용합니다. 긴 명령을 명령행에 직접 넣지 않으며 추가 PowerShell 프로세스를 중첩하지 않습니다. 로컬 실행기는 Windows PowerShell 5.1에서도 호출할 수 있지만 명령 실행에는 설치된 PowerShell 7이 필요합니다. `-RequireAdministrator`는 현재 토큰만 확인하며 UAC를 자동 승인하지 않습니다.

- Windows: `~/.config/opencode/strata-client/bin/opencode-strata.ps1`
- macOS: `~/.config/opencode/strata-client/bin/opencode-strata`

연결과 설정 상태를 다시 확인하려면 `setup` 대신 `doctor`를 전달합니다.

```powershell
.\tools\remote_agent_client\setup-windows.bat doctor
```

```sh
sh tools/remote_agent_client/setup-macos.sh doctor
```

`doctor`는 API 키 값을 출력하지 않습니다. 키 파일 존재/권한, OpenCode provider-model 및 CUA MCP 매핑, CUA 실행 파일 버전, `/health`, `/v1/models`, Rider ACP 등록을 점검합니다. 실제 생성 응답, tool call, 이미지 요청, Rider 세션, Hermes, 실제 CUA 화면 조작은 별도 검증입니다. `doctor`가 PASS여도 macOS 권한 승인이나 화면 조작 성공을 의미하지 않습니다.

## 설정되는 파일

| 위치 | 내용 |
| --- | --- |
| `~/.config/opencode/strata-client/secrets/STRATA_API_KEY` | 이 클라이언트용 API 키. macOS/Linux는 secrets 디렉터리와 파일을 사용자 전용으로 제한하고, Windows는 사용자 ACL 적용 |
| `~/.config/opencode/strata-client/opencode.jsonc` | 서버와 정확한 모델 ID를 지정하는 V2 사용자 오버레이 |
| `~/.config/opencode/strata-client/KOREAN_INSTRUCTIONS.md` | 한국어 작업 지침 사본 |
| `~/.config/opencode/strata-client/bin/` | `OPENCODE_CONFIG`를 설정하는 OS별 CLI/ACP wrapper |
| `~/.config/opencode/strata-client/setup-state.json` | 비밀이 아닌 서버·모델·경로 상태 |
| `~/.config/opencode/opencode.json`의 `rea` MCP 등록 | REA 공식 setup이 백업 후 추가하는 고정 버전 `rea-agents@6.7.0` 실행 등록 |
| `~/.agents/skills/reverse-engineer-anything` | REA 공식 setup이 설치하는 분석 지침과 참조 자료 |
| OpenCode 오버레이의 `mcp.servers.cua-driver` | 창 단위 정책을 적용하는 Node 중계기 |
| `~/.jetbrains/acp.json` | 기존 agent를 보존하고 추가한 OpenCode Strata ACP 항목 |

기존 OpenCode 전역 `opencode.json`과 `opencode.jsonc`는 수정하지 않습니다. OpenCode의 `OPENCODE_CONFIG` 사용자 설정 오버레이는 전역·프로젝트 설정과 병합되며, 생성 overlay에는 OpenCode V2의 portable agent profile, Strata provider, 서버가 보고한 모델 ID가 들어갑니다. 프로젝트별 `opencode.json(c)`가 같은 키를 정의하면 그 설정이 우선할 수 있습니다. [V2 설정 위치와 병합](https://dev.opencode.ai/v2/docs/config/), [V2 provider](https://opencode.ai/v2/docs/providers/), [V2 파일 변수](https://dev.opencode.ai/v2/docs/config/)

기존 `acp.json`이 있으면 백업을 만든 뒤 다른 agent 항목을 보존합니다. 같은 이름이 이미 사용 중이면 새 항목에 `(2)` 같은 이름을 붙입니다. 기존 ACP 파일을 JSON으로 읽을 수 없으면 덮어쓰지 않고 중단합니다.

## REA

- REA는 로컬 파일, .NET 어셈블리, JavaScript/Electron 앱, 웹 페이지와 사용자가 권한을 가진 바이너리를 근거 중심으로 분석하는 MCP입니다. 실행 파일·DLL·설치 프로그램·APK·Electron/ASAR 등 권한 있는 바이너리 아티팩트의 분석·검사·역공학·비교 요청에서는 `rea_analysis` subagent가 자동 선택되며, `@rea_analysis`로 직접 호출할 수도 있습니다. 일반 소스 코드·문서·이미지는 REA가 필요한 형식일 때만 위임합니다. 분석 대상의 라이선스와 권한은 사용자가 확인해야 합니다.
- 설치기는 REA OpenCode 등록과 분석 지침만 추가합니다. REA CLI를 전역 설치하지 않으며, MCP는 고정된 npm 패키지를 `npx`로 시작합니다. 터미널 일회성 실행은 `npx -y rea-agents@6.7.0 --help`를 사용하세요.
- `doctor`는 REA의 OpenCode 등록과 분석 지침만 범위 지정해 확인합니다. Ghidra, IDA, Hopper, JADX, Kuna가 설치되지 않은 경고는 해당 네이티브 분석 기능이 미구성이라는 뜻이며 OpenCode MCP 등록 실패로 취급하지 않습니다.
- 재설치 후 REA를 사용하려면 setup에서 기본 선택을 수락하고 OpenCode와 Rider를 완전히 재시작하세요. 일반 Build 세션에는 `rea_*` 도구를 노출하지 않아 REA의 큰 도구 목록이 매 요청 컨텍스트를 불필요하게 차지하지 않습니다. 기존 OpenCode 설정의 REA 백업은 REA가 `opencode.json.rea.backup`으로 관리합니다.

## CUA와 Hermes

- CUA Driver는 Strata 원격 API와 별개로, 화면을 조작할 클라이언트 PC에 설치됩니다. 이 설정 도구는 공식 Windows/macOS 설치기를 동의 후 실행하고, OpenCode 오버레이의 `mcp.servers.cua-driver`에 Node 중계기와 로컬 드라이버 절대 경로를 등록합니다. OpenCode 프로필의 `cua-driver_*` 허용 규칙도 실제 등록 도구에 적용됩니다.
- Windows에서는 OpenCode가 `cua-driver mcp`를 실행하면 해당 프로세스가 자체 런타임을 소유합니다. macOS에서는 MCP 클라이언트가 실행 중인 CuaDriver.app 데몬에 연결해야 합니다. 설치 직후 앱을 띄우며 권한 안내를 표시할 수 있지만, 화면 기록·손쉬운 사용 권한은 사용자가 System Settings에서 직접 승인해야 하고 `doctor`도 이를 PASS로 표시하지 않습니다.
- 설정 후 OpenCode를 완전히 재시작하세요. Rider ACP는 설정된 OpenCode wrapper를 사용하지만 실제 Rider 세션에서 CUA 도구가 호출되는지는 별도 검증이 필요합니다. macOS에서 로그아웃/재부팅 후 데몬이 꺼져 있으면 `open -n -g -a CuaDriver --args serve`로 시작하고 `cua-driver permissions grant`를 다시 실행하세요.
- 설치기는 CUA Driver만 다룹니다. CUA CLI, Spaces, 로그인, 전역 skill 설치는 수행하지 않습니다. CUA Driver는 콘텐츠를 포함하지 않는 제품 사용 telemetry를 기본 전송한다고 공식 문서에 안내하므로 원하지 않으면 `cua-driver telemetry disable`을 실행하세요.
- Hermes는 별도 사용자 설정을 가집니다. `hermes model`에서 Custom endpoint를 선택하고 Strata URL과 확인된 model ID를 입력하세요. Hermes의 API 키는 Hermes가 지원하는 로컬 비밀 저장 절차로 입력하세요. 이 도구는 Hermes YAML을 수정하지 않습니다.

## 백업과 복원

2026-10-22 Windows 검증: 기존 icacls 옵션 조합의 오류와 PowerShell 모듈 경로에 따른 Set-Acl 로딩 실패를 확인했다. 현재 사용자 SID만 허용하는 DACL을 .NET으로 한 번에 적용하도록 수정했다. 한글·공백 경로의 격리 설치에서 키 ACL 확인과 실제 OpenCode v2.0.22의 `run -- --version` 실행이 성공했다. 이 시험은 실제 원격 모델 생성·CUA 조작·REA MCP 분석·Mac 실기를 포함하지 않는다.

다시 `setup`을 실행하면 변경되는 생성 설정과 `acp.json`은 타임스탬프 백업을 만듭니다. API 키 파일은 키가 백업에 남지 않도록 백업하지 않습니다. 설치를 되돌리려면 Rider의 `OpenCode Strata` ACP 항목만 제거하고, 필요할 때 타임스탬프 백업에서 `acp.json`을 복원한 다음 `~/.config/opencode/strata-client/`만 제거합니다. API 키를 더 이상 쓰지 않을 때에는 `~/.config/opencode/strata-client/secrets/STRATA_API_KEY`만 별도로 제거하세요.

이 도구는 Windows와 macOS에서 Strata 인증·모델 목록 및 CUA 실행 파일/MCP 설정을 점검합니다. 실제 Strata 생성 요청, 장기 262K 세션, OpenCode tool call, Rider GUI 대화, Hermes ACP, macOS 권한 승인, CUA 화면 인식·조작은 자동 검증하지 않습니다.

## 통합 개선 (2026-10-19)

[빠른 시작](../../docs/OPENCODE_QUICKSTART_KO.md)을 기준으로 설치하세요. 현재 설치기는 기본 200단계(사용자 지정 예산 보존), 자동 압축, 한국어 지침과 제한 시간 실행기를 함께 설치합니다. revision 6부터 플러그인·ACP 보조 파일은 해시별 버전 경로를 사용하고, revision 7부터 단계 예산을 갱신합니다. CUA는 background만 허용하며 foreground 재시도와 GUI 앱 자동 실행은 차단합니다. Mac 실제 동작과 Rider/Hermes 검증은 이번 작업에서 수행하지 않았습니다.
