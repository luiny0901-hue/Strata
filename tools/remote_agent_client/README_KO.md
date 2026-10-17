# Windows/Mac 원격 Strata 클라이언트 설정

이 도구는 이미 실행 중인 Windows Strata 서버를 Windows 또는 Apple Silicon Mac의 OpenCode와 Rider에 연결합니다. OpenCode의 OpenAI 호환 provider만 설정하며 Strata, 모델, 방화벽, GPU, CUA Driver를 설치하거나 변경하지 않습니다.

## 필요한 것

- Python 3
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

도구가 서버 주소와 키를 묻습니다. 키는 숨김 입력이며, 먼저 `/health`와 인증된 `/v1/models`를 확인합니다. 모델 ID는 서버 응답에서 선택하므로 프로필 이름을 추측하지 않습니다. 여러 모델이 있으면 목록에서 선택합니다. context와 이미지 capability는 `/health`가 반환한 값만 사용합니다.

설정이 끝나면 Rider를 재시작하고 AI Chat의 agent 선택기에서 `OpenCode Strata`를 고릅니다. OpenCode 터미널 작업은 다음 wrapper를 사용합니다.

- Windows: `~/.config/opencode/strata-client/bin/opencode-strata.ps1`
- macOS: `~/.config/opencode/strata-client/bin/opencode-strata`

연결과 설정 상태를 다시 확인하려면 `setup` 대신 `doctor`를 전달합니다.

```powershell
.\tools\remote_agent_client\setup-windows.bat doctor
```

```sh
sh tools/remote_agent_client/setup-macos.sh doctor
```

`doctor`는 API 키 값을 출력하지 않습니다. 키 파일 존재/권한, OpenCode provider-model 매핑, `/health`, `/v1/models`, Rider ACP 등록을 점검합니다. 실제 생성 응답, tool call, 이미지 요청, Rider 세션, Hermes, CUA 화면 조작은 별도 검증입니다.

## 설정되는 파일

| 위치 | 내용 |
| --- | --- |
| `~/.config/opencode/strata-client/secrets/STRATA_API_KEY` | 이 클라이언트용 API 키. macOS/Linux는 secrets 디렉터리와 파일을 사용자 전용으로 제한하고, Windows는 사용자 ACL 적용 |
| `~/.config/opencode/strata-client/opencode.jsonc` | 서버와 정확한 모델 ID를 지정하는 V2 사용자 오버레이 |
| `~/.config/opencode/strata-client/KOREAN_INSTRUCTIONS.md` | 한국어 작업 지침 사본 |
| `~/.config/opencode/strata-client/bin/` | `OPENCODE_CONFIG`를 설정하는 OS별 CLI/ACP wrapper |
| `~/.config/opencode/strata-client/setup-state.json` | 비밀이 아닌 서버·모델·경로 상태 |
| `~/.jetbrains/acp.json` | 기존 agent를 보존하고 추가한 OpenCode Strata ACP 항목 |

기존 OpenCode 전역 `opencode.json`과 `opencode.jsonc`는 수정하지 않습니다. OpenCode의 `OPENCODE_CONFIG` 사용자 설정 오버레이는 전역·프로젝트 설정과 병합되며, 생성 overlay에는 OpenCode V2의 portable agent profile, Strata provider, 서버가 보고한 모델 ID가 들어갑니다. 프로젝트별 `opencode.json(c)`가 같은 키를 정의하면 그 설정이 우선할 수 있습니다. [V2 설정 위치와 병합](https://dev.opencode.ai/v2/docs/config/), [V2 provider](https://opencode.ai/v2/docs/providers/), [V2 파일 변수](https://dev.opencode.ai/v2/docs/config/)

기존 `acp.json`이 있으면 백업을 만든 뒤 다른 agent 항목을 보존합니다. 같은 이름이 이미 사용 중이면 새 항목에 `(2)` 같은 이름을 붙입니다. 기존 ACP 파일을 JSON으로 읽을 수 없으면 덮어쓰지 않고 중단합니다.

## CUA와 Hermes

- CUA Driver는 해당 클라이언트 PC에서 별도로 제공되어야 합니다. 도구는 CUA 설치 파일이나 명령을 모르므로 설치·등록·화면 조작을 자동화하지 않습니다.
- Rider ACP의 custom MCP 공유는 활성화됩니다. 이는 Rider가 이미 가진 custom MCP 도구를 전달하는 설정입니다. OpenCode 쪽 CUA 도구가 실제로 등록돼 있는지, 어떤 명령으로 동작하는지는 OpenCode의 해당 클라이언트에서 확인해야 합니다.
- OpenCode 프로필의 `cua-driver_*` 허용 규칙은 같은 이름의 도구가 등록되어 있을 때만 적용됩니다. macOS CUA 지원은 미검증입니다.
- Hermes는 별도 사용자 설정을 가집니다. `hermes model`에서 Custom endpoint를 선택하고 Strata URL과 확인된 model ID를 입력하세요. Hermes의 API 키는 Hermes가 지원하는 로컬 비밀 저장 절차로 입력하세요. 이 도구는 Hermes YAML을 수정하지 않습니다.

## 백업과 복원

다시 `setup`을 실행하면 변경되는 생성 설정과 `acp.json`은 타임스탬프 백업을 만듭니다. API 키 파일은 키가 백업에 남지 않도록 백업하지 않습니다. 설치를 되돌리려면 Rider의 `OpenCode Strata` ACP 항목만 제거하고, 필요할 때 타임스탬프 백업에서 `acp.json`을 복원한 다음 `~/.config/opencode/strata-client/`만 제거합니다. API 키를 더 이상 쓰지 않을 때에는 `~/.config/opencode/strata-client/secrets/STRATA_API_KEY`만 별도로 제거하세요.

이 도구는 이 OS에서 Strata로 인증하고 모델 목록을 읽는 설정 점검을 지원합니다. 실제 Strata 생성 요청, 장기 262K 세션, OpenCode tool call, Rider GUI 대화, Hermes ACP, CUA Driver, Apple Silicon CUA는 자동 검증하지 않습니다.
