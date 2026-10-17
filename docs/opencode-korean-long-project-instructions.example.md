# OpenCode Korean and long-project instructions

- Reply in Korean unless the user explicitly requests another language.
- Before changing a repository, read its `AGENTS.md` and current task or handoff notes. Inspect only files related to the requested slice.
- Break long work into small, verifiable steps. Record completed work, actual validation, unresolved items, and the next step in the repository's existing handoff document when one exists.
- After context compaction or a new chat, resume from those notes. Do not repeat discovery or commands whose inputs have not changed.
- If the same command or tool action fails twice without a meaningful change, stop repeating it, inspect the failure, and report the blocker or a safer alternative.
- Preserve unrelated user changes and data. Do not claim a test, build, or feature passed unless it actually ran and passed.
- Before finishing, summarize changed files, commands actually run, failures and retries, unverified behavior, and the next safe step.

### 프로그램 실행과 테스트

- 실행 전에 프로젝트 문서에서 테스트 명령과 필요한 런타임을 확인한다. Windows는 `Get-Command`, WSL/Linux는 `command -v`로 실제 실행 파일 경로와 버전을 확인한다. 없는 도구를 Windows PATH의 shim으로 대신 실행하거나, 요청 없이 설치하지 않는다.
- 테스트·빌드는 비대화형으로 실행하고 사용자 입력을 기다리는 설치 프로그램, watch 모드, 개발 서버를 테스트 명령으로 실행하지 않는다.
- Windows에서는 PowerShell 7을 명시하고 `~/.config/opencode/scripts/run_bounded_command.ps1`를 사용한다. 기본 제한은 900초이며 빠른 테스트는 300초로 줄인다. 예: `& "$env:USERPROFILE\.config\opencode\scripts\run_bounded_command.ps1" -WorkingDirectory (Get-Location).Path -TimeoutSeconds 300 -Command 'npm test'`.
- WSL/Linux에서는 `~/.config/opencode/scripts/run_bounded_command.sh`로 실행한다. Windows OpenCode에서 WSL 테스트를 요청할 때는 `wsl.exe -d Ubuntu -- bash -lc 'bash ~/.config/opencode/scripts/run_bounded_command.sh --timeout 900 -- python3 -m unittest -v'`처럼 Linux 셸과 Linux 작업 디렉터리를 명시한다.
- WSL에서 `opencode`가 Windows 실행 파일로 연결될 수 있다. `opencode debug paths`와 `file "$(command -v opencode)"`로 확인하고, Windows OpenCode가 Linux 셸을 자동으로 쓴다고 가정하지 않는다. `node`가 없는 WSL에서 Windows `npm` shim을 Linux Node 테스트로 표시하지 않는다.
- 실행기는 stdin을 닫고 stdout/stderr를 별도 로그에 보존하며 제한 시간 초과 시 자신이 만든 프로세스 트리만 종료한다. 종료 코드와 로그 경로를 확인한다. 시간 초과 뒤 같은 명령을 다시 띄우지 말고 로그와 해당 프로세스 상태를 먼저 조사한다.
- 테스트 중 출력이 없으면 같은 프로세스의 진행 상태를 확인한다. 중복 실행을 만들지 않는다. 시간 초과나 실패는 근거와 함께 기록하고, 원인 변경 없이 같은 테스트를 반복하지 않는다.
