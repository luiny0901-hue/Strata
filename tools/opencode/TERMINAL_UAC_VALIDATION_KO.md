# 터미널·UAC 처리 보완 — 2026-10-21

Windows에서 실제 확인한 실패를 수정했습니다. `Write-Error`와 `Read-Host`가 실패했는데도 기존 실행기가 EXIT_CODE=0을 반환했고, heartbeat 메시지는 1초 이상 실행되는 일부 경우 문자열 형식 오류를 일으켰습니다.

## 적용 경로

- Rider ACP: `OPENCODE_ACP_TERMINAL_GUARD=1`일 때 PowerShell 명령을 UTF-8 BOM 임시 파일로 전달하고 공통 bootstrap/preflight로 실행합니다. 기존 shell 도구의 timeout/취소/프로세스 트리를 그대로 사용합니다. 임시 스크립트는 호출 종료 시 정리합니다. 새 프로세스에 추가 옵션을 상속하도록 설치기가 ACP 항목을 갱신하므로 재시작이 필요합니다.
- 직접 실행: `run_bounded_command.ps1 -Command '명령' -WorkingDirectory '작업 경로' -TimeoutSeconds 900`. 긴 코드는 `-CommandFile 'UTF-8.ps1'`을 사용합니다. Windows PowerShell 5.1에서 호출해도 설치된 pwsh 7로 명령을 실행합니다.
- 로그는 시작 전 파일을 열고 stdout/stderr를 파일로 복사하며, 미리보기만 24000자로 제한합니다. 완료 후 출력 파이프 대기는 5초, 시간 초과 후 프로세스 종료 대기는 15초로 제한합니다. 정리를 확인하지 못하면 성공으로 보고하지 않습니다.
- Git 자격 증명 프롬프트 및 일반 stdin 입력을 비대화형으로 제한합니다. 명령이 조용하더라도 heartbeat를 출력하고 중복 실행하지 않습니다.
- Linux/macOS Bash 실행기에는 INT/TERM/HUP 처리와 소유한 GNU timeout 프로세스 그룹 정리, 직접 sudo/gsudo/runas 호출 차단을 추가했습니다. 137을 무조건 timeout으로 바꾸지 않습니다. 실제 Linux/macOS 프로세스 그룹 회귀 테스트는 이 Windows 세션에서 실행하지 않았습니다.

## 관리자 작업

`-RequireAdministrator`는 현재 Windows 토큰이 관리자 권한인지 검사합니다. 권한이 없으면 실제 명령 실행 전에 코드 77/BLOCKED_UAC로 끝나며 승인 창을 열지 않습니다. 이미 권한 있는 컨텍스트에서 사용자가 요청한 작업은 현재 권한으로 실행할 수 있습니다. RunAs·대화형 비밀번호를 자동 입력하거나 UAC를 끄는 설정, 관리자 예약 작업·권한 상승 서비스는 만들지 않습니다.

일반 프로그램의 비관리자 확인은 UAC와 다릅니다. 제한 시간 안의 확인은 같은 호출에서 완료하고, timeout 후 늦은 확인은 종료한 프로세스를 재시작하지 않습니다. 새 요청에서는 현재 파일·프로세스 상태부터 확인합니다.

종료 코드: 0 성공, 일반 명령의 원래 비정상 종료 코드 보존, 2 파싱 실패, 73 로그 준비 실패, 77 관리자/승인 차단, 124 시간 초과, 125 정리 또는 출력 수집 미확인, 126 시작 실패, 127 pwsh/GNU timeout 없음. 외부 프로그램이 같은 코드를 직접 반환할 수도 있으므로 결과 메시지와 로그도 함께 판단합니다.

## 검증

Windows 실행기 12개 테스트: 정상/비정상 종료, PowerShell 오류, 대화형 입력, 직접·축약형·동적 Verb UAC 요청 차단, 관리자 토큰 검사, 지연 확인, timeout 후 늦은 확인 미실행, 200000자 로그와 제한된 미리보기, 한글·공백 경로 및 Windows PowerShell 5.1에서 긴 파일 실행, timeout 후 소유 자식 PID 종료를 확인했습니다. 실제 UAC 보안 데스크톱을 띄우거나 클릭하지 않았습니다.

설치된 OpenCode 2.0.22 + 로컬 모의 모델의 ACP 검증:

| 사례 | 결과 | diagnostics 폴더 |
|---|---|---|
| 네이티브 PowerShell 정상 실행 | 기존 background 차단/전경 출력/최종 보고 유지 | terminal-native-bootstrap-1 |
| UAC 요청 | 실제 권한 상승 전에 BLOCKED_UAC, 대체 일반 작업 및 후속 요청 정상 | terminal-native-uac-1, terminal-native-uac-optin |
| PowerShell 오류 | 오류가 모델에 전달되고 후속 작업 정상 | terminal-native-error-1 |
| 대화형 입력 | NonInteractive 실패 후 후속 작업 정상 | terminal-native-interactive-1 |
| 긴 명령 | 70000자 이상의 원문을 짧은 실행 경로로 전달해 완료 | terminal-native-long-1, terminal-native-long-optin |
| 취소 및 늦은 알림 | 남은 파일쓰기 미실행, 자동 재개 차단, 새 요청 정상 | terminal-native-cancel-1 |
| 연결 종료 | 소유 shell PID 종료, 남은 작업 미실행 | terminal-native-disconnect-1 |

실제 Strata GPU 부하, Rider 화면, 실제 Windows UAC 승인/취소, WSL 배포판 및 Apple Silicon 앱은 별도 미검증입니다. 자동 승인 없이 모든 관리자 작업이 끝난다고 주장하지 않습니다.

실패 시도: 변경 전 PowerShell 오류/Read-Host의 두 테스트가 0 종료로 실패한 것을 확인했습니다. 첫 지연 확인 테스트에서는 기존 heartbeat의 `-f` 포맷 인자 결합 오류로 실행기가 실패했으며 괄호를 보완한 뒤 통과했습니다. 실패 결과를 정상 결과로 대체해 숨기지 않습니다.

재현: `python -m unittest tools.test_opencode_terminal_runners -v`, ACP 사례는 `tools/test_acp_foreground_runtime.py --fault uac|powershell-error|interactive|long-command` 또는 `--cancel`, `--disconnect`에 바이너리와 새 output 폴더를 지정합니다.

## 불필요한 대기 점검 (2026-10-21)

- 네이티브 OpenCode shell은 timeout 0이면 무제한이다. ACP guard에서 명시적 0을 코어 기본과 같은 120000ms로 보정하고 광고 스키마에도 양수 제한을 표시했다. 명시한 420000ms와 생략된 기본값은 그대로 보존한다. 조용한 출력만으로 작업을 중단하는 idle timeout은 추가하지 않았다.
- PowerShell 승격 사전 검사에 -V/-Ve/-Ver 축약형을 추가했다. 실제 보안 데스크톱을 띄우기 전에 BLOCKED_UAC로 끝낸다. 우회 가능한 모든 스크립트를 차단하는 보안 경계라고 주장하지 않는다.
- 대기 지침에 짧은 조회 15~30초, 일반 명령 기본 120초, 긴 작업은 명시적 유한 기한을 적었다. 고정 sleep 대신 실제 준비 조건을 확인하고 충족 즉시 진행하도록 했다. 이 부분은 모델 지침이며 모든 생성 명령에 기계적으로 강제되지 않는다.
- Node ACP guard 검사 통과. Windows 실행기 테스트 묶음 12개 실행, Linux 클래스 1개 건너뜀, 실패 없음. 설치된 OpenCode + 모의 모델 UAC 및 후속 요청 정상: diagnostics/terminal-wait-uac-20261021.
- 별도 실제 Windows 실행기 단회 측정(프로세스 시작 비용 포함): 짧은 성공 1.221초/exit0, 축약형 UAC 0.532초/exit77, Read-Host 1.145초/exit1, 30초 sleep에 1초 제한 1.650초/exit124. 반복 통계나 실제 앱 설치창 측정은 아니다.
- 설치된 ACP 플러그인/사전 검사/전역 지침 갱신. 재시작 후 적용. 원래 실행기 자체의 기본 900초 및 명시적 긴 작업 제한은 변경하지 않았다.
