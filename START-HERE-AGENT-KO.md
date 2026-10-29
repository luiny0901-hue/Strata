# 처음 사용하는 분께

## 처음 설치·재설치: 통합 설치기

- Windows: **`INSTALL-STRATA-AGENT.bat`**를 실행합니다. 접속 PC 또는 NVIDIA 서버 복구·준비를 선택합니다.
- Apple Silicon Mac: **`bash install-strata-agent.sh`**를 실행합니다. 실행 권한이 있는 `INSTALL-STRATA-AGENT.command`도 같은 설치기를 엽니다.
- Linux NVIDIA 서버: **`bash install-strata-agent.sh --role server`**를 실행합니다.

필요한 Python·Node.js·Claude Desktop·OpenCodex·CUA·REA 준비와 연결 설정을 한 흐름으로 진행하며, 이미 설치된 항목과 기존 설정을 재사용합니다. 서버의 동일 포크·모델·Pack은 백업 복원 자료를 사용합니다. OS 승인·로그인·GPU 드라이버 재부팅·서버 복구 파일·SSH/VPN 준비가 필요한 단계는 대기로 남기고 같은 설치기를 다시 실행해 이어갑니다.

**[통합 설치 안내와 자동/수동 단계](docs/INTEGRATED_INSTALL_KO.md)**를 먼저 확인하세요. 이미 사용 중인 환경의 설정만 다시 적용하려면 아래 기존 설정기를 사용합니다.


## Claude Desktop Code로 작업하기

현재 권장 경로는 **Claude Desktop Code → OpenCodex 프록시 → Strata 서버**입니다.

컨텍스트 창은 262,144토큰이며 응답·자동 압축 버퍼는 창 안에 확보합니다. 설정 적용 후 새 Code 세션에서 262.1k 표시를 확인합니다.

1. 평소 사용하는 `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat` 또는 `...-off.bat`로 Strata를 실행합니다.
2. OpenCodex 프록시가 실행 중인지 확인합니다.
3. 연결 설정을 적용하려면 `setup-claude-opencodex.bat`를 실행합니다. 설정은 Claude 형식의 `~/.claude/strata-mcp.json`을 사용하며 CUA·REA를 필요할 때 검색해 실행합니다.
4. Claude Desktop의 **Code**에서 작업 폴더를 열고 신뢰 확인을 마칩니다.
5. 모델 선택기에서 **Strata (OpenCodex)**를 선택합니다. MCP 연결과 권한 모드의 확인은 각각 완료합니다.

설치·외부 PC 연결·진단은 [Claude Desktop Code 연결 안내](docs/CLAUDE_OPENCODEX_KO.md)를 따르세요. 터미널 Claude Code 실행기는 별도이며 Desktop Code 화면을 열지 않습니다.

Codex도 함께 사용하려면 기존 Claude 연결을 마친 뒤 `setup-claude-opencodex.bat clients`를 실행합니다. Strata의 공통 모델 정보와 Codex의 지연 MCP·한국어 지침을 연결하고, 기존 모델 선택·권한은 보존합니다. `clients --check`는 변경 없이 차이를 확인합니다. [클라이언트별 적용 범위](docs/STRATA_CLIENT_SETTINGS_20261028_KO.md)를 확인하고 새 Codex 세션에서 연결을 확인하세요.

Claude Desktop Code에서 웹 페이지 읽기는 `WebFetch`를 사용할 수 있습니다. 내장 웹 검색이 Strata 경로에서 실패할 때 선택형 검색을 설정하는 방법은 [웹 검색 안내](docs/CLAUDE_WEB_SEARCH_KO.md)를 참고하세요.

## 실행 환경을 유지보수할 때

Claude Desktop Code에서 이 Strata 저장소 폴더를 열고 새 세션을 시작합니다. `strata-maintenance` MCP는 이 프로젝트에서만 사용할 수 있습니다. 일반 앱·게임 개발 폴더에는 불러오지 않습니다. 유지보수 프로젝트에서도 필요 없으면 `/mcp`에서 끄고 다음에 다시 켤 수 있으며, 설정 재적용은 그 선택을 보존합니다.

Windows에서 Desktop 재시작 뒤 남은 작업까지 이어가려면 `setup-desktop-restart.bat`를 한 번 실행하고 Strata 관리 실행기를 다시 시작합니다. 작업 중에는 에이전트가 체크포인트를 저장한 뒤 재시작을 요청합니다. Desktop을 닫은 동안 같은 Claude Code의 임시 재개 실행이 남은 작업을 처리하고 원래 대화를 다시 엽니다. [재시작·복구 안내](docs/CLAUDE_SELF_MAINTENANCE_KO.md)의 지원 범위와 취소 방법을 확인하세요.

## 새 PC에서 연결하기

서버와 접속 PC의 역할을 먼저 구분하세요. **모델·Pack·GPU는 서버에만**, Claude Desktop·OpenCodex·CUA·REA는 실제 작업할 Windows 또는 Apple Silicon Mac에 둡니다. Mac에서 같은 대형 모델을 다시 구동할 필요가 없습니다.

1. 접속 PC에 최신 저장소와 [Claude Desktop](https://claude.com/download), [Python 3.10 이상](https://www.python.org/downloads/), [Node.js LTS](https://nodejs.org/en/download), [CUA Driver](https://cua.ai/docs/cua-driver/quickstart)를 준비합니다. REA의 고정 버전 실행기는 포함되어 있으며 필요한 패키지는 첫 사용 때 준비합니다. 실제 역분석에 필요한 별도 도구는 REA의 요구 조건을 따릅니다.
2. 접속 PC에 OpenCodex를 설치하고 Strata 공급자와 Claude Desktop 게이트웨이를 설정합니다. 같은 PC의 서버는 `127.0.0.1:8080`, 외부 서버는 아래 연결 안내의 SSH 터널을 사용합니다.
3. Windows는 `setup-claude-opencodex.bat`, Mac은 `bash setup-claude-opencodex.sh`를 실행합니다. Mac용 `setup-claude-opencodex.command`도 같은 설정기를 실행하며 결과 창을 유지합니다. 새 MCP 설정이 없으면 설치된 CUA·Node.js를 찾아 안전한 CUA·REA 기본 연결을 생성하므로 다른 PC의 JSON을 직접 작성할 필요가 없습니다.
4. 기존의 사용자 지정 MCP가 필요하면 `--mcp-config`로 Claude 형식 파일을 가져옵니다. 기존 Claude 소유 MCP 파일이 있으면 먼저 그 설정을 보존합니다. 경로는 새 PC에서 재지정하며, 비밀 키·작업 파일·기존 대화는 별도 보관/복원 대상입니다.
5. Claude Desktop Code의 새 세션에서 폴더 신뢰·MCP 연결·OS 권한을 확인합니다. Mac의 접근성·화면 기록 권한은 사람이 허용해야 합니다.

설정기는 Claude Desktop·OpenCodex·Node.js·CUA와 서버 모델을 전부 자동 설치하는 프로그램은 아닙니다. 누락된 실행 환경은 설치 주소를 안내하며 준비되지 않은 상태를 성공으로 보고하지 않습니다. [OS별 준비·외부 연결·재설치 절차](docs/CLAUDE_OPENCODEX_KO.md#새-pc재설치외부-pc)를 확인하세요.

서버 PC를 초기화하는 경우에는 Strata 코드, ON/OFF 프로필, 동일 버전 포크 엔진·모델·Pack 파일과 서버 설정을 별도로 복원해야 합니다. 서버 준비는 [AI 설치 안내](docs/AI_SETUP.md)와 [Linux 서버 안내](docs/LINUX_NVFP4_SERVER_KO.md)를 참고하세요.

## Strata 서버 실행

`run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat`은 요청된 비검열 설정으로, `...-off.bat`은 기본 설정으로 실행합니다. 이미 서버가 실행 중이면 다시 시작하지 마세요. 서버 자체를 변경하는 작업은 [관리 재시작 안내](docs/STRATA_MANAGED_RESTART_KO.md)의 체크포인트와 대기 규칙을 따릅니다.

## Strata 안정판 자동 업데이트

서버 복구 자료를 준비한 뒤 `SETUP-STRATA-UPDATES.bat`에서 켜기·끄기·상태 확인을 선택할 수 있습니다. 하루 한 번 확인하며 준비된 새 버전은 다음 서버 시작 때 적용합니다. 실행 중 작업은 중단하지 않습니다. 충돌·기동 실패 시 동작은 [자동 업데이트 안내](docs/STRATA_FORK_AUTO_UPDATE_KO.md)를 확인하세요.
