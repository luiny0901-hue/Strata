# Windows Strata를 Rider와 Hermes에서 사용하기

이 안내서는 Windows에서 실행하는 Strata API를 Windows 또는 macOS의 OpenCode, Rider, Hermes에서 사용하는 방법을 정리합니다. 모델 실행 파일과 모델 데이터는 Strata 호스트에만 둡니다. macOS 클라이언트가 이 Windows CUDA/NVFP4 실행 파일을 직접 실행하는 구성은 아닙니다.

## 현재 구성에서 확인된 경계

- 이 저장소의 UD-IQ4_XS NVFP4 실행 BAT은 Windows에서 `0.0.0.0:8080`으로 API를 열고 `STRATA_API_KEY` 인증을 요구합니다.
- 이 PC의 OpenCode 설정은 `127.0.0.1:8080`을 가리킵니다. 이는 같은 Windows PC의 Rider/OpenCode에 맞는 주소이며, 다른 PC나 Mac에서 그대로 쓸 수 없습니다.
- OpenCode와 Hermes는 Strata 호스트가 아니라 클라이언트 기기에서 실행됩니다. 각 기기의 로컬 프로젝트 경로, 터미널, IDE 도구, MCP 설정은 해당 클라이언트에 따로 있어야 합니다.
- Strata는 OpenAI 호환 `/v1/chat/completions`와 도구 호출 API를 제공합니다. Hermes의 사용자 지정 endpoint는 이 형식과 연결할 수 있습니다. 실제 Rider/Hermes 대화 및 도구 실행은 별도로 확인해야 합니다.
- 모델의 현재 API ID는 클라이언트에서 `GET /v1/models`로 확인해 사용합니다. `262144` context limit는 서버 프로필에 설정된 상한이며, 262K 전체 길이 작업의 안정성이나 성능을 입증하지 않습니다.

Hermes는 Windows 10/11과 Apple Silicon macOS를 공식 지원 대상으로 안내합니다. Rider의 ACP 연결은 IDE와 에이전트가 같은 Windows 또는 Mac에서 실행되는 구성이며, 각 OS에 맞는 에이전트 실행 파일이 필요합니다. [Hermes 플랫폼 지원](https://hermes-agent.nousresearch.com/docs/getting-started/platform-support), [JetBrains ACP 안내](https://www.jetbrains.com/help/ai-assistant/acp.html)

## 네트워크 주소와 API 키

| 실행 위치 | Strata 기본 URL |
| --- | --- |
| Strata와 같은 Windows PC | `http://127.0.0.1:8080/v1` |
| 다른 Windows PC 또는 Mac, 같은 신뢰 가능한 LAN | `http://<Windows 호스트의 LAN 주소>:8080/v1` |
| 다른 네트워크에서 Tailscale 사용 | `http://<Windows 호스트의 Tailscale 주소>:8080/v1` |

클라이언트 PC의 `127.0.0.1`은 그 클라이언트 자신을 뜻합니다. 원격 클라이언트에선 Windows 호스트 주소를 넣어야 합니다. DHCP로 바뀔 수 있는 주소 대신 공유기 예약 주소 또는 Tailscale 주소를 사용하세요.

서버 BAT은 Windows 방화벽 검사도 수행합니다. 현재 검사 스크립트는 활성 네트워크가 Private이어야 하고, Domain/Public 네트워크에서 TCP 8080을 차단하며, Windows Firewall이 모든 프로필에서 켜져 있어야 시작을 허용합니다. Tailscale 규칙은 스크립트가 새로 만들지 않습니다. 현재 Tailscale 인터페이스 주소에 한정된 기존 `Tailscale-In` 규칙이 Private 프로필 조건을 통과해야 하며, 기존 규칙은 Strata 포트 외의 연결도 허용할 수 있으므로 Tailscale ACL을 별도로 확인해야 합니다. 이 조건이 맞지 않으면 방화벽을 끄거나 범위를 넓히지 말고, 우선 신뢰 가능한 Private LAN에서 사용하세요.

Strata API는 여기서 일반 HTTP로 연결됩니다. 인터넷에 포트 포워딩하거나 공개 네트워크에 직접 노출하지 마세요. Tailscale 밖의 신뢰할 수 없는 네트워크에서는 이 설정을 사용하지 마세요.

API 키는 서버 호스트의 `%USERPROFILE%\.config\strata\STRATA_API_KEY`에 저장되어 있습니다. 키 값을 저장소, 채팅, 커밋된 설정에 넣지 마세요. 각 클라이언트 기기의 비밀 저장 위치에 키를 따로 입력해야 합니다. macOS 키 파일은 `chmod 600 ~/.config/strata/STRATA_API_KEY`로 사용자만 읽도록 제한하세요.

## OpenCode와 Rider 연결

Rider는 ACP를 통해 **로컬에 설치된 OpenCode**를 시작합니다. Strata 주소와 모델은 그 Windows/Mac의 OpenCode 설정에 둡니다. JetBrains ACP 설정 파일은 각 사용자 홈의 `~/.jetbrains/acp.json`이며 `command`는 해당 기기에 설치된 실행 파일의 절대 경로여야 합니다. Windows의 `C:\Users\...\opencode.exe` 경로를 Mac에 복사하면 작동하지 않습니다. [OpenCode ACP 안내](https://docs.opencode.ai/docs/acp/)

현재 OpenCode V2의 `providers` 형식 예시입니다. `<STRATA_HOST>`를 위 표의 주소로 바꾸고, 모델 ID는 서버의 `/v1/models` 응답에서 복사하세요. 이 예시의 `apiKey`는 키 값이 아니라 클라이언트의 키 파일을 읽는 참조입니다. V2 provider/model 설정 방식은 [OpenCode V2 Providers](https://opencode.ai/v2/docs/providers)와 [OpenCode Config](https://docs.opencode.ai/docs/config/)를 기준으로 했습니다.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "strata/ud-iq4-xs",
  "providers": {
    "strata": {
      "name": "Strata",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "http://<STRATA_HOST>:8080/v1",
        "apiKey": "{file:~/.config/strata/STRATA_API_KEY}",
        "headerTimeout": 600000,
        "chunkTimeout": 600000
      },
      "models": {
        "ud-iq4-xs": {
          "modelID": "<GET /v1/models 의 정확한 id>",
          "name": "Unsloth UD-IQ4_XS on Windows Strata",
          "capabilities": {
            "tools": true,
            "input": ["text", "image"],
            "output": ["text"]
          },
          "limit": {
            "context": 262144,
            "output": 32000
          },
          "variants": [
            { "id": "none", "body": { "reasoning_effort": "none" } },
            { "id": "low", "body": { "reasoning_effort": "low" } },
            { "id": "medium", "body": { "reasoning_effort": "medium" } },
            { "id": "high", "body": { "reasoning_effort": "high" } }
          ]
        }
      }
    }
  }
}
```

`headerTimeout`와 `chunkTimeout`은 대용량 prompt 처리 중 OpenCode가 연결을 너무 일찍 끊지 않도록 10분으로 늘린 값입니다. 실제 지연시간을 보증하지 않습니다. 서버가 이미지 기능을 `/health`에서 보고하지 않으면 `image` 입력 capability를 빼세요. Strata가 받는 `reasoning_effort` 값은 `none`, `low`, `medium`, `high`입니다. `xhigh`, `max`, `ultra`는 보내지 마세요.

## 대규모 저장소용 컨텍스트와 자율 권한

OpenCode는 저장소의 모든 소스 파일을 매 요청마다 컨텍스트에 자동 삽입하지 않습니다. 세션에는 전역·프로젝트 AGENTS.md와 지정한 지침이 먼저 들어가고, 하위 디렉터리의 AGENTS.md는 해당 영역을 탐색할 때 추가됩니다. 소스 내용은 검색 및 파일 읽기 도구로 불러옵니다. 따라서 관련 모듈부터 좁혀 보라는 지침은 도움이 되지만, 모델이 넓게 검색하지 못하도록 강제하는 격리는 아닙니다. [지침 로딩 방식](https://dev.opencode.ai/v2/docs/instructions/)과 [파일 도구](https://opencode.ai/docs/tools/)를 참고하세요.

전역 설정을 복원할 때 [OpenCode V2 설정 조각](../examples/opencode/autonomous-agent-v2.fragment.json)과 [한국어 지침 템플릿](../examples/opencode/KOREAN_INSTRUCTIONS.md)을 사용합니다. 두 파일은 Windows와 macOS에서 동일하게 쓸 수 있습니다. 예제에는 사용자 비밀값, 개인 절대경로, 로컬 CUA 설치 정보를 넣지 않았습니다.

- 설정 조각의 최상위 항목을 기존 opencode.json에 병합하세요. providers, endpoint, 모델, 키 참조가 들어 있는 기존 값을 덮어쓰지 마세요.
- 한국어 지침 파일을 사용자 설정 디렉터리의 KOREAN_INSTRUCTIONS.md로 복사하고, 기존 instructions 배열에 해당 경로를 추가하세요.
- 파일 읽기·검색·편집 및 프로젝트 셸 작업은 자동 허용하고, 비밀 파일, 프로젝트 밖 접근, 대표적인 삭제·초기화, 커밋·푸시·GitHub CLI 작업은 승인 대상으로 둡니다.
- 셸은 허용된 코드 실행기이지 보안 샌드박스가 아닙니다. 명령 패턴 승인 규칙은 래퍼나 다른 명령으로 우회될 수 있으므로 OS 계정과 저장소 경계를 유지하세요.
- 기본 build 에이전트의 단계 한도는 100이고, 자동 압축은 최근 20,000 토큰을 유지합니다. 압축 요약은 일부 세부사항을 잃을 수 있으므로 긴 작업은 저장소의 이슈·인계 문서에 진행 상태를 남기세요.
- 262K는 요청 컨텍스트의 상한입니다. 실제 요청마다 그 길이를 채우거나 장기 작업의 품질을 보증하는 설정은 아닙니다.


각 OS에서 로컬 OpenCode CLI 경로를 확인한 뒤 Rider의 ACP 설정에 등록합니다. OpenCode의 ACP 명령은 `opencode acp`입니다. 아래 경로는 예시일 뿐이므로 각 PC의 설치 경로로 교체합니다.

```json
{
  "default_mcp_settings": {
    "use_custom_mcp": true,
    "use_idea_mcp": false
  },
  "agent_servers": {
    "OpenCode Strata": {
      "command": "<이 PC의 OpenCode 절대 경로>",
      "args": ["acp"]
    }
  }
}
```

JetBrains의 IDE MCP 도구가 필요하면 Rider에서 MCP 서버를 활성화하고 `use_idea_mcp`를 `true`로 설정하세요. OpenCode의 custom MCP와 Hermes의 MCP는 별도 설정이며 Strata API를 통해 전달되지 않습니다.

## Hermes 단독 사용 또는 Rider에서 Hermes 사용

Hermes 설정은 OpenCode에서 복사되지 않습니다. 각 Windows/Mac에서 `hermes model`의 Custom endpoint 설정을 사용해 **Chat Completions** 형식을 선택하고 Strata 주소, API 키, `/v1/models`의 정확한 모델 ID를 입력하면 됩니다. 공식 문서는 `/v1/chat/completions`를 제공하는 OpenAI 호환 API를 사용자 지정 endpoint로 지원합니다. [Hermes 사용자 지정 endpoint 안내](https://hermes-agent.nousresearch.com/docs/integrations/providers)

수동 설정 예시 (`%USERPROFILE%\.hermes\config.yaml` 또는 `~/.hermes/config.yaml`):

```yaml
model:
  provider: custom
  default: "<GET /v1/models 의 정확한 id>"
  base_url: "http://<STRATA_HOST>:8080/v1"
  key_env: STRATA_API_KEY
  context_length: 262144

agent:
  reasoning_effort: high
```

`key_env` 값은 `%USERPROFILE%\.hermes\.env` 또는 `~/.hermes/.env`에 다음처럼 저장합니다.

```dotenv
STRATA_API_KEY=<클라이언트에 안전하게 입력한 키>
```

`context_length`는 서버에서 확인한 실제 제한보다 크게 설정하지 마세요. Strata가 허용하는 추론 단계는 `none`, `low`, `medium`, `high`이므로 `high`를 넘는 Hermes 수준을 선택하면 요청이 거부될 수 있습니다.

Rider에서 Hermes를 쓰려면 Hermes ACP 추가 기능을 설치하고 해당 PC에서 `hermes acp --check`가 통과해야 합니다. JetBrains ACP 설정의 agent 항목은 다음 형태입니다. Hermes 설정과 키는 ACP가 실행되는 같은 PC의 `~/.hermes/` 아래에 둡니다. [Hermes ACP 안내](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp/)

```json
{
  "agent_servers": {
    "Hermes Strata": {
      "command": "<이 PC의 Hermes 절대 경로>",
      "args": ["acp"]
    }
  }
}
```

JetBrains는 ACP 실행 파일을 Rider의 자식 프로세스로 시작하므로 설치된 실행 파일 경로가 OS마다 다릅니다. macOS의 `~/.local/bin/hermes` 같은 경로와 Windows의 Hermes 실행 경로를 각각 해당 기기에 맞춰 등록하세요. Rider를 macOS에서 사용할 때 프로젝트 파일은 Mac에 있어야 합니다. Strata 호스트는 텍스트/이미지/도구 호출 요청을 처리할 뿐 프로젝트 파일을 Mac으로 제공하지 않습니다.

## CUA와 실제 검증의 경계

Rider, OpenCode, Hermes의 Strata 연결은 모델 API 연결입니다. GUI 조작용 CUA Driver는 별도 로컬 MCP/도구이며 Windows 설정이 Mac으로 자동 전달되지 않습니다. 이 저장소의 현재 CUA Driver가 macOS에서 지원되는지는 확인되지 않았습니다.

이 문서는 설정 경로와 계약만 정리합니다. 실제 Windows/Mac 네트워크 연결, `/health`, `/v1/models`, 도구 호출, 이미지 입력, Rider 대화, Hermes ACP, 262K 장기 작업은 실행하지 않았으며 모두 사용자가 별도로 검증해야 합니다.
