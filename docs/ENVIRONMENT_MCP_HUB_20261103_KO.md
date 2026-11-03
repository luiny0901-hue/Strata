# 4클라이언트 공통 MCP 도구 허브 (2026-11-03)

네 코딩 클라이언트(Claude CLI, Claude Desktop Code, Codex CLI, ChatGPT Desktop)가 하나의 MCP Control(`agent-tools`)에서 같은 개발 조사 도구를 쓰도록 확장한 기록이다. 모델 연결(OpenCodex 10100 → Strata 8080)은 그대로 두었고, 바꾼 쪽은 MCP 도구 경로만이다.

## 목표 구조

```
[Claude CLI / Desktop Code / Codex CLI / ChatGPT Desktop]
        └─ OpenCodex(10100) ─ Strata(8080) ─ 로컬 LLM        ← 모델 연결 (변경 없음)
        └─ agent-tools 디스패처(MCP Control, stdio)
              ├─ Web Search(SearXNG 8888 등 라우터)          ← 기존 유지
              ├─ cua-driver / rea(자식 stdio)                 ← 기존 유지
              └─ toolsetServers: github · context7 · huggingface · arxiv · openalex · serena · unity · unreal
```

OpenCodex는 모델 연결·프로토콜 중계만 담당하고 MCP 도구를 실행하지 않는다. 도구 실행은 각 클라이언트가 stdio로 붙은 `agent-tools`를 통해 한다.

## 조사된 현재 환경 (2026-11-03)

| 항목 | 확인 값 |
|---|---|
| OpenCodex | `@bitkyc08/opencodex` 2.95.0(npm), 작업 스케줄러 서비스 `opencodex-proxy`, 포트 10100(bun), 소유 정보 `~/.opencodex/service-state.json` |
| Strata | `serve.server` 포트 8080(프로필 strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-on-1m), 제어 8768, 모델 `qwen3.8-flash-next-unsloth-ud-iq4_xs`(text+image, reasoning, 1M 창) |
| 웹 검색 백엔드 | SearXNG(Docker, 127.0.0.1:8888, healthz 200) |
| 런타임 | node v24.22.1, npm 11.19.1, uv/uvx 0.13.1, git 2.55.0, PowerShell 기본 |
| 클라이언트 | claude 2.1.308(`~/.local/bin/claude.exe`), codex-cli 0.166.0-alpha.5.1 |
| 엔진 | Unity CLI 1.0.0-beta.12 + 에디터 6.0.85f1/6.3.27f2/6.7.0b7/7.0.0a12, UE_5.8(`C:\Program Files\Epic Games\UE_5.8`) |
| Codex 설정 위치 | `CODEX_HOME` 미설정 → 기본 `C:\Users\luiny\.codex` (Codex CLI와 ChatGPT Desktop 공통) |

클라이언트 연결 파일: Claude 사용자 범위 `~/.claude.json`(agent-tools) + 프로젝트 범위 `~/.claude.json` projects(strata-maintenance), Codex·ChatGPT Desktop `~/.codex/config.toml`의 `[mcp_servers."agent-tools"]`(strata-client-mcp 블록). Desktop Code는 이 두 Claude 파일을 그대로 사용한다. 설정 4종(`.claude.json`, `strata-mcp.json`, `.codex/config.toml`, `.opencodex/config.json`) 백업: `C:\Users\luiny\Strata-data\config-backups\2026-11-03-mcp-env\`.

## 디스패처 확장 (MCP Control)

기존 `agent-tools`는 CUA·REA 전용이었다(`search_tools`/`call_tool`의 서버 열거형 고정). 이번 변경으로 설정 파일의 `toolsetServers` 항목이 같은 검색·호출 표면에 합류한다.

- 저장소 변경: `tools/claude_mcp/lazy_dispatcher.py`(동적 서버 열거형·summary 노출), `tools/claude_mcp_config.py`(`toolsetServers` 검증·보존 — 설정 재적용 시 소실 안 함), 테스트 갱신·추가. 커밋 `89d0337d`.
- 검사: `python -m unittest tools.test_claude_mcp_lazy_dispatcher tools.test_claude_mcp_dispatcher_bounds` 40개 통과, `tools.test_claude_opencodex_client` 84개 통과, `tools.test_claude_mcp_rea_launcher` 2개 통과 (Strata 가상환경 파이썬, 2026-11-03).
- 동작: 도구가 필요한 서버만 `search_tools` 선택 시점에 시작한다. 클라이언트 컨텍스트에는 항상 `search_tools`·`call_tool`(+`web_search`) 2~3개 스키마만 노출되므로 서버 추가에 따른 컨텍스트 증가가 없다.
- 정본 설정: `~/.claude/strata-mcp.json`의 `toolsetServers`(각 항목 stdio command/args/env/summary). CLI 클라이언트는 새 세션부터 반영되고 열린 세션은 시작 시점의 설정을 유지한다. Claude Desktop 앱은 앱이 시작한 디스패처 연결을 Code 세션 간에 공유하므로, 앱 종료 후 재실행하거나 `/mcp`에서 `agent-tools`를 재연결해야 새 등록이 보인다(2026-11-03 실측: 검증용 새 Code 세션이 변경 전 디스패처 연결을 그대로 사용).
- Streamable HTTP 공통 서버는 새로 만들지 않았다. 네 클라이언트 모두 stdio 디스패처에 이미 연결돼 있어 중복이다. 필요해진 시점에 디스패처에 HTTP 수신 추가를 검토한다(미구축).

## 등록된 도구 서버

| 서버 | 실행 | 버전·라이선스 | 인증 | 실측 결과 (2026-11-03) |
|---|---|---|---|---|
| github | `~/.local/bin/github-mcp-server/github-mcp-server.exe stdio --read-only --toolsets=context,issues,pull_requests,repos,users` | v2.1.0(2026-11-03 릴리스, zip sha256 검증), MIT | gh CLI 인증 자동 사용(키링 gho_, repo 범위). PAT 복사 없음 | 도구 27개, `get_me`·`search_repositories` 성공 |
| context7 | `node.exe …npm\node_modules\@upstash\context7-mcp\dist\index.js`(전역 설치) | 4.5.0, MIT | 키 없음 = 저쿼터(키 있으면 상향, `CONTEXT7_API_KEY`) | `resolve-library-id`·`query-docs` 성공(Next.js 미들웨어 최신 문서 확인) |
| huggingface | `node.exe …@llmindset/hf-mcp-server\dist\server\stdio.js`(전역 설치) | 0.4.32, MIT | `DEFAULT_HF_TOKEN`(기존 `~/.cache/huggingface/token`의 OAuth 토큰을 env에 주입 — 코드가 읽는 변수명은 이쪽이고 `HF_TOKEN`은 안내 문구용. 만료 시 `hf auth login` 후 갱신) | 토큰 반영 확인(`hf_whoami` → @luiny0901), `hub_repo_search` 성공 |
| arxiv | `npx -y @cyanheads/arxiv-mcp-server@1.8.1` | 1.8.1(2026-10-29), Apache-2.0 | 불필요 | `arxiv_search_papers` 성공(MoE 논문 반환) |
| openalex | `npx -y mcp-remote@0.16.0 https://mcp.openalex.org/mcp` | 공식 호스팅(코드 MIT, 데이터 CC0) | openalex.org 계정 OAuth 서명 1회, 이후 본인 API 키($1/일 크레딧)로 실행. 토큰은 `~/.mcp-auth` 캐시 | 도구 18개 목록 + `search_works` 실호출 성공(rerank된 논문 반환, 2026-11-03) |
| serena | `~/.local/bin/serena.exe start-mcp-server --project-from-cwd --enable-web-dashboard false` | serena-agent 2.1.0(`uv tool install -p 3.13`), GPL-3.0 | 불필요(로컬) | REPL·`find_symbol`·`get_symbols_overview` 성공. 단 프로젝트 등록(`serena project create <dir> --ls <언어>`) 후 사용 |
| unity | `unity.exe mcp` | Unity CLI 1.0.0-beta.12(최신 beta.15), Pipeline 패키지 0.9.1-exp.1 | Unity 로그인(에디터가 패키지 다운로드 시 세션 만료로 실패할 수 있음 — `unity auth login` 후 Retry) | 에디터 실측 성공(2026-11-03, 재확인 11-04): 6.6.7f1 실행 중 허브 자식 서버가 도구 110개 노출(CLI `unity list` 기준 166), `get_hierarchy`가 SampleScene 루트·컴포넌트까지 반환 — CLI(`unity status`)는 현재 폴더 기준이지만 `unity mcp` 서버는 실행 중인 에디터를 전역으로 찾아, 다른 폴더의 Code 세션에서도 도구가 보인다(도구 0개인 경우는 에디터 미실행일 때뿐임) |
| unreal | `npx -y mcp-remote@0.16.0 http://127.0.0.1:8000/mcp`(stdio→HTTP 브리지) | mcp-remote 0.16.0, MIT | 불필요 | UE 5.8 공식 Unreal MCP(실험, HTTP/SSE만 지원) 연결 경로 확인. 에디터 종료 시 "접속 오류" 정상 보고. UE_5.8 설치에 `ModelContextProtocol`+`ToolsetRegistry` 플러그인 동봉 확인(파일 기준). 에디터 실행 중 도구 호출은 미측정 |

미설치 항목과 근거:

- **GitHub 원격 서버/원격 프록시 미사용**: 로컬 바이너리로 동일 기능(읽기 전용·toolset 필터)을 커버.
- **GitNexus 미설치**: Serena와 기능 중복, 추가 이점 확인 전까지 보류. **Playwright 미설치**: CUA와 웹 브라우저 자동화가 겹치고 Codex·Desktop은 자체 브라우저 플러그인 보유. **Crawl4AI 미설치**: 원문 조회는 기존 웹검색 경로(web_search+fetch)로 확인됐고 필요 시점에 재검토.
- **Unity AI Assistant 인-에디터 MCP 서버**: 공식 폐기(deprecated) 상태라 설치하지 않았다(공식 문서). 대체가 이번 `unity mcp` 경로.

## 클라이언트 연결과 검증

- **Codex CLI**: `codex exec`로 agent-tools→search_tools→call_tool(github) 및 context7 3단계 시나리오 성공(총 27,243·29,178토큰). `CODEX_HOME` 미설정이므로 `~/.codex/config.toml`이 실제 사용 경로다.
- **Claude CLI**: 사용자 범위 설정에서 agent-tools 공유. 단 Desktop 전용 `CLAUDE_*`·`ANTHROPIC_*` 변수를 제거한 격리 실행(`claude -p`)에서만 정상(기존 관측과 동일). arxiv 도구 호출 성공(exit 0).
- **Claude Desktop Code**: 같은 `~/.claude.json`/`strata-mcp.json`을 사용하므로 설정 공유를 확인했다. 새 Code 세션은 앱이 시작한 디스패처 연결을 공유하므로 등록 변경 후 앱 재시작/`/mcp` 재연결이 필요하다. 2026-11-03 재연결 후 재시험에서 arxiv·github 도구 검색, web_search(SearXNG 경로), CUA 회귀가 모두 성공했다.
- **ChatGPT Desktop**: Codex와 같은 `~/.codex`를 쓰기 때문에 설정은 자동 공유한다. 2026-11-03 실측: 앱을 켜 새 Codex 작업(Strata 모델)에서 `search_tools(server="github")` 요청 프롬프트를 CUA로 전달(백그라운드 `set_value` + 백그라운드 클릭; Chromium 창은 백그라운드 키입력이 차단되고 이 클라이언트에는 전경 승인 창이 없음)했고, 모델이 github 서버 도구 5개(search_code 등 — 읽기 전용 toolset 구성과 일치)를 정확히 보고했다(작업 24초). 생성된 대화 한 건만 남고 파일 변경은 없었다.
- 모든 테스트에서 OpenCodex→Strata 응답 경로가 유지됨(에러·차단 없음).
- 기존 3기능 유지 확인(2026-11-03): `web_search`(SearXNG 라우터)는 Desktop Code에서 실제 검색 성공, CUA는 도구 검색 회귀 통과, REA는 207개 도구 연결에 `open_binary` 실분석 성공. `binary_overview`은 최초 provider 미설치(진단 아래)였고 Ghidra 설치 후 git.exe 대상 완전 개요 반환으로 실측 통과.
- REA 분석 엔진 설치(2026-11-03, 사용자 승인): Ghidra 12.1.4(진단이 검증 버전으로 지정한 12.1.x 최신) + Temurin JDK 21.0.13+9를 포터블 형태로 `C:\Users\luiny\Tools`에 배치, 사용자 환경변수로 `GHIDRA_INSTALL_DIR`·`JAVA_HOME`·`%JAVA_HOME%\bin`(PATH 선행) 설정. `rea doctor`의 ghidra 계열 9항목 healthy 전환, 허브 자식 서버 경유 `binary_overview(git.exe)` 실분석 성공. 9MB급 Go 바이너리는 기본 330초(`REA_GHIDRA_STARTUP_TIMEOUT_MS`)로는 첫 분석이 타임아웃되므로 큰 대상은 값을 올리거나 대상마다 다르다. **설치한 환경변수는 새 프로세스부터 적용**되므로, 설치 전에 시작된 클라이언트의 REA 세션은 재시작 전까지 여전히 provider 없음으로 본다.

## 사용 규칙 (요약)

- 기술 조사: `web_search`(SearXNG 로컬 우선) → 근거는 원문(공식 문서·GitHub) 확인. 라이브러리 API는 `context7`, 오픈소스 구현·커밋·릴리스는 `github`, 모델·데이터셋·논문은 `huggingface`, 논문은 `arxiv`·`openalex`(저자·기관·인용·분석은 openalex), 현재 프로젝트 구조는 `serena`(프로젝트 등록 후), 엔진은 `unity`/`unreal`(각 에디터 실행 중) 순서로 선택.
- 로컬·무료 우선: 추가 유료 키 필수 항목 없음. Context7 무료 한도(키 있으면 월 1,000호출), GitHub는 gh 토큰 스코프 내 읽기 전용. 429·403 시 재시도·쿨다운은 웹검색 라우터 기준을 따른다.
- 게임 엔진: 단순 조회·빌드·테스트는 Unity CLI(`unity status`/`command`/`build`/`test`) 우선, MCP(`unity mcp`)는 실행 중 에디터 조작용. CLI(`unity status`/`command` 등)는 현재 폴더(또는 `--project-path`) 기준으로 에디터를 찾고, MCP 서버는 실행 중인 에디터를 전역으로 붙는다(11-04 재확인). Unreal은 에디터에서 Auto Start Server 또는 `ModelContextProtocol.StartServer` 실행 후 사용(5.8 공식 플러그인, 실험 단계).

## 유지보수

- 서버 추가/삭제: `~/.claude/strata-mcp.json`의 `toolsetServers` 수정(이름은 소문자-하이픈, summary 필수, type은 stdio만). 검증: `C:\Users\luiny\Strata\.venv\Scripts\python.exe -I -c "import sys,pathlib;sys.path.insert(0,r'C:\Users\luiny\Strata-opencode-session-recovery');from tools import claude_mcp_config;print(sorted(claude_mcp_config.read(pathlib.Path.home()/'.claude/strata-mcp.json')['toolsetServers'])))"`. 설정기 재적용(load_claude_mcp_source)에서도 보존된다.
- 디스패처·설정기 검사 묶음: 위 "검사" 항목의 unittest 명령.
- Unity·Unreal·Serena는 상태 의존형이라 에디터/프로젝트 준비가 먼저다: Unity는 프로젝트에 Pipeline 패키지(`unity pipeline install`) 후 에디터 실행, Unreal은 플러그인(`Unreal MCP`+`All Toolsets`) 활성화 후 `ModelContextProtocol.StartServer`, Serena는 `serena project create <프로젝트> --ls <언어>`.
- OpenAlex: 서명 토큰은 `~/.mcp-auth`에 캐시되고 첫 연결 때 브라우저 서명 창이 열린다. 연결 초기화는 서명 보유 인스턴스가 콜백 포트 20400을 소유하므로, 잔류 mcp-remote가 있으면 새 인스턴스는 대기만 한다 — 초기화하려면 `~/.mcp-auth`의 openalex 항목과 잔류 프로세스를 정리 후 다시 연결한다. 무료 크레딧($1/일) 소진은 계정 페이지에서 확인한다.
- Unity 재측정: 테스트 프로젝트 `C:\Users\luiny\UnityProjects\mcp-hub-check`(6.6.7f1, Pipeline 설치됨)를 `unity open`으로 열고 프로젝트 폴더에서 `unity status`/`list`를 실행하면 된다(에디터 종료 후 재열기 시 패키지 인증 오류가 나면 `unity auth login` 후 Retry). 실측 뒤 에디터는 `unity close .`(프로젝트 폴더에서)로 정상 종료 확인.
- Unreal: UE_5.8 엔진에 공식 `ModelContextProtocol`+`ToolsetRegistry` 플러그인 동봉을 파일 기준으로 확인함(2026-11-03). 에디터 실행 중 호출 실측은 실제 UE 프로젝트-opening 시점에 `ModelContextProtocol.StartServer` 후 진행(실험 기능).
- REA 분석 엔진(2026-11-03 진단; 명령: `node %LOCALAPPDATA%\npm-cache\_npx\<hash>\node_modules\rea-agents\scripts\rea.mjs doctor` — rea-agents@6.7.0은 npm 캐시 실행이라 `rea` CLI가 PATH에 없음): Hopper·Ghidra·IDA·jadx·Kuna가 모두 미설정으로 `missing_analysis_engine` — 그래서 `open_binary`(내장 로더)는 동작하고 `binary_overview` 등 심층 분석만 provider 오류를 낸다(기존 상태이며 이번 변경과 무관). 무료 경로인 Ghidra 12.1.x 설치 후 `GHIDRA_INSTALL_DIR` 지정이 진단이 권하는 방법. 그 외 doctor의 `registration:claude_code` config_drift는 on-demand 디스패처 모드가 정본인 환경에서 예상되는 항목.
- 남은 문제: ① Unreal 에디터 실행 중 도구 호출 실측(위), ② 생성 지침(`~/.claude/CLAUDE.md`)의 'CUA·REA 전용' 문장은 생성물이라 설정 재적용 시점에 갱신(정본 `examples/claude/KOREAN_INSTRUCTIONS.md`는 이번 턴에 고쳤으나 해당 파일의 진행 중 작업과 함께 커밋될 예정), ③ Unity CLI는 beta.15가 최신이나 이번 작업 범위 밖이라 올리지 않았다,⑤ 해결(2026-11-04): 앱 세션의 search→call 가드 리셋은 원인 특정 완료 — Desktop 프로필 `configLibrary\57dfacd4-….json`의 `managedMcpServers."Strata tools (local)"`과 사용자 설정 `~/.claude.json`의 `agent-tools`가 같은 디스패처의 중복 등록이라 앱 재시작 후 서버 2개가 모두 떠 요청이 분산된 것(검색 상태가 다른 프로세스에 남음). 터미널 Claude CLI는 사용자 설정 쪽이 필요하므로, 정리 방향은 Desktop 세션에서 둘 중 하나만 남기는 것 — `/mcp` 패널에서 서버 하나 비활성화가 가장 간단하며, 프로필 측 managed 항목 제거는 설정기(백업·diff) 경로로 진행한다. 단일 등록인 Codex CLI·직접 프로브는 계속 정상이었고, REA 엔진 경로는 `strata-mcp.json`의 `mcpServers.rea.env`(GHIDRA_INSTALL_DIR·JAVA_HOME)에 고정해 어떤 재시작 환경에도 의존하지 않는다. 정리 후 재시작한 앱 세션에서 최종 재확인(2026-11-04): 서버가 `agent-tools` 하나로 접속되고 search→`open_binary`→`binary_overview` 체인이 통과했다(git.exe, 13세그먼트·함수 182·문자열 237, `upstream_analysis_profile.provider=ghidra 12.1.4`, 이후 `close_binary`로 세션 정리). 백업: `Strata-data\config-backups\2026-11-04-mcp-dedup\`.
