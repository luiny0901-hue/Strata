# 처음 사용하는 분께

## Claude Desktop Code로 작업하기

현재 권장 경로는 **Claude Desktop Code → OpenCodex 프록시 → Strata 서버**입니다.

컨텍스트 창은 262,144토큰이며 응답·자동 압축 버퍼는 창 안에 확보합니다. 설정 적용 후 새 Code 세션에서 262.1k 표시를 확인합니다.

1. 평소 사용하는 `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat` 또는 `...-off.bat`로 Strata를 실행합니다.
2. OpenCodex 프록시가 실행 중인지 확인합니다.
3. 연결 설정을 적용하려면 `setup-claude-opencodex.bat`를 실행합니다. 설정은 Claude 형식의 `~/.claude/strata-mcp.json`을 사용하며 CUA·REA를 필요할 때 검색해 실행합니다.
4. Claude Desktop의 **Code**에서 작업 폴더를 열고 신뢰 확인을 마칩니다.
5. 모델 선택기에서 **Strata (OpenCodex)**를 선택합니다. MCP 연결과 권한 모드의 확인은 각각 완료합니다.

설치·외부 PC 연결·진단은 [Claude Desktop Code 연결 안내](docs/CLAUDE_OPENCODEX_KO.md)를 따르세요. 터미널 Claude Code 실행기는 별도이며 Desktop Code 화면을 열지 않습니다.

Claude Desktop Code에서 웹 페이지 읽기는 `WebFetch`를 사용할 수 있습니다. 내장 웹 검색이 Strata 경로에서 실패할 때 선택형 검색을 설정하는 방법은 [웹 검색 안내](docs/CLAUDE_WEB_SEARCH_KO.md)를 참고하세요.

## 실행 환경을 유지보수할 때

Claude Desktop Code에서 이 Strata 저장소 폴더를 열고 새 세션을 시작합니다. `strata-maintenance` MCP는 이 프로젝트에서만 사용할 수 있습니다. 일반 앱·게임 개발 폴더에는 불러오지 않습니다. 유지보수 프로젝트에서도 필요 없으면 `/mcp`에서 끄고 다음에 다시 켤 수 있으며, 설정 재적용은 그 선택을 보존합니다.

Windows에서 Desktop 재시작 뒤 남은 작업까지 이어가려면 `setup-desktop-restart.bat`를 한 번 실행하고 Strata 관리 실행기를 다시 시작합니다. 작업 중에는 에이전트가 체크포인트를 저장한 뒤 재시작을 요청합니다. Desktop을 닫은 동안 같은 Claude Code의 임시 재개 실행이 남은 작업을 처리하고 원래 대화를 다시 엽니다. [재시작·복구 안내](docs/CLAUDE_SELF_MAINTENANCE_KO.md)의 지원 범위와 취소 방법을 확인하세요.

## 새 PC에서 연결하기

1. 최신 저장소를 내려받아 압축을 풉니다.
2. 새 PC에 Claude Desktop, Node.js, Python, 그리고 사용할 CUA Driver·REA 실행 환경을 준비합니다.
3. 해당 PC의 Claude MCP 설정 파일을 준비하고 `setup-claude-opencodex.bat --mcp-config "경로\strata-mcp.json"`으로 적용합니다.
4. Strata 서버와 OpenCodex 프록시 주소·실행 상태를 확인한 뒤 Claude Desktop Code에서 새 세션을 엽니다.

서버 PC를 초기화하는 경우에는 Strata 코드, ON/OFF 프로필, 모델·Pack 파일과 서버 설정을 별도로 복원해야 합니다. 서버 준비는 [AI 설치 안내](docs/AI_SETUP.md)와 [Linux 서버 안내](docs/LINUX_NVFP4_SERVER_KO.md)를 참고하세요.

## Strata 서버 실행

`run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat`은 요청된 비검열 설정으로, `...-off.bat`은 기본 설정으로 실행합니다. 이미 서버가 실행 중이면 다시 시작하지 마세요. 서버 자체를 변경하는 작업은 [관리 재시작 안내](docs/STRATA_MANAGED_RESTART_KO.md)의 체크포인트와 대기 규칙을 따릅니다.
