# Rider ACP 백그라운드 완료 유실 방지

OpenCode 2.0.22의 ACP는 첫 응답 종료 시 열린 자식 세션이 없으면 이벤트 구독을 닫습니다. 이후 백그라운드 shell 완료가 세션을 재개해도 Rider로 후속 보고가 전달되지 않을 수 있습니다.

이 플러그인은 `OPENCODE_ACP_FOREGROUND_GUARD=1`인 프로세스에서 `shell(background=true)`를 실행 전에 차단하고, 실행되지 않았다는 결과를 모델에 반환합니다. 유한 검증은 충분한 timeout을 지정한 전경 호출로 다시 실행하게 합니다. 일반 전경 호출과 환경변수가 없는 CLI는 그대로 통과합니다. 무한 서비스 명령을 임의로 전경으로 전환하지 않습니다.

설치: 저장소에서 `python tools/configure_acp_foreground_guard.py` 실행 후 Rider의 ACP 연결을 다시 시작합니다. 설치기는 기존 설정과 다른 연결을 보존하고 변경 전 백업을 만듭니다. 다른 설치 위치는 `--config`, `--acp`로 지정합니다. OpenCode v2 전용이며, 기존 OpenCode ACP 항목이 있어야 합니다.

이는 문제를 유발한 호출을 차단하는 실행 보호 장치입니다. OpenCode 바이너리의 일반적인 백그라운드 구독 문제를 수정한 것은 아닙니다. 이미 시작한 백그라운드 작업, 수동 background 전환, 다른 종류의 비동기 작업까지 복구하지 않습니다.

## 2026-10-21 확인

- 설치된 OpenCode 2.0.22 ACP + 로컬 모의 모델: 차단 대상 파일 미생성, 차단 결과 모델 전달, 후속 전경 shell 출력 및 최종 응답이 end_turn 전에 도착함을 확인.
- Node 단위 확인: 활성/비활성 및 전경 호출 통과.
- 기존 session recovery 단위 테스트: 11개 통과.
- 실제 Rider 화면과 Strata 모델을 통한 회귀 실행은 하지 않음. 기존 사용자 세션은 종료하지 않음.
- 시도 이력: 테스트 스크립트 최초 문법 오류 수정. 첫 런타임 시도는 제목 생성 요청을 작업 요청으로 세어 검증 실패. 제목 요청을 분리한 두 번째 시도 통과. 실패 기록은 diagnostics/acp-guard-attempt1에 보존, 통과 기록은 diagnostics/acp-guard-attempt2에 보존.

검증 명령: `node tools/test_acp_foreground_guard.mjs`. 실제 설치 바이너리 검증은 `python tools/test_acp_foreground_runtime.py --binary <opencode.exe> --output <새 진단 디렉터리>`이며 별도 DB와 로컬 모의 모델을 사용합니다.

## 완료 이후 실행과 자식 작업 보호

같은 날 추가 조사에서 subagent의 background=true와 늦은 synthetic 완료 알림도 부모 ACP 응답이 종료된 뒤 실행을 이어갈 수 있음을 소스에서 확인했습니다. shell만 제한하던 범위를 보완했습니다.

- shell background=true는 계속 실행 전에 차단합니다. subagent는 background 요청 여부에 관계없이 결과를 기다리는 호출로 전달합니다. 자식 작업을 끝낸 뒤 부모가 최종 보고합니다. 서로 독립된 전경 도구의 병렬 호출은 별도 제한하지 않습니다.
- 추가 환경변수 `OPENCODE_ACP_TURN_GUARD=1`을 설치기가 기존 OpenCode ACP 항목에 설정합니다. 새 프로세스에서만 활성화되므로 기존 프로세스의 실행 도중 새 게이트가 소급 적용되지 않습니다.
- user/awaited-child prompt가 해당 세션의 추론을 허용합니다. 같은 실행 안의 도구 호출, 모델 재요청, 출력 잘림 복구는 허용합니다. 세션의 종료 시각이 바뀐 뒤 새 prompt 없이 시작하려는 primary 모델 요청은 `ACP_OUT_OF_TURN_BLOCKED` 오류로 모델 HTTP 전송 전에 차단합니다. 늦은 자동 알림의 실행 시도는 DB에 실패한 실행으로 남을 수 있으며, 기존 최종 보고는 보존됩니다. 새 사용자의 후속 요청은 다시 허용합니다.
- title/compaction/generate는 이 primary 실행 게이트에 포함하지 않습니다. 짧은 제목 생성 같은 보조 요청과 실제 코드 작업은 구분해야 합니다. 이미 분리해서 실행한 상시 서비스나 예전 프로세스의 작업을 이 설치가 소급 종료하지는 않습니다.

설치된 OpenCode 2.0.22 ACP를 격리 DB와 로컬 모의 모델로 검증한 사례:

1. 백그라운드 셸 차단 후 전경 처리와 최종 응답 전달.
2. end_turn 후 늦은 synthetic 알림 → 추가 모델 HTTP 0회 → 같은 세션 후속 요청 1회 정상 실행.
3. 실행 중 shell 취소 → cancelled 응답, 남은 파일쓰기 미실행 → 늦은 알림 차단 → 후속 요청 정상 실행.
4. 실제 subagent(background=true) 요청 → 자식 결과가 부모에게 전달된 뒤 end_turn, pending/inbox 비어 있음.
5. 실제 자식 shell 실행 중 부모 취소 → 남은 파일쓰기 미실행, 새 후속 요청 정상 실행.
6. length로 잘린 write → 기존 출력 복구와 충돌 없이 작은 파일 실제 저장 및 end_turn.
7. ACP stdin EOF → ACP 프로세스 종료, 소유 shell PID 종료, 남은 파일쓰기 미실행.

추가 재현 옵션은 `--late-resume`, `--cancel`, `--subagent`, `--subagent --cancel`, `--output-recovery`, `--disconnect`입니다. 각 실행에 새 `--output` 경로를 지정합니다. 최초 late-resume 검증에서는 모델 HTTP가 실제로 2회에 머물고 늦은 실행도 실패했으나, 테스트가 오류 문자열이 message 행에 저장된다고 가정해 실패했습니다. 모델 요청 전 실패는 assistant message를 만들지 않으므로 마지막 idle outcome 및 HTTP 요청 수로 관측을 수정했고 재검증에 통과했습니다. 실패 폴더 `diagnostics/acp-turn-late-resume-1`과 통과 폴더 `diagnostics/acp-turn-late-resume-2`를 보존했습니다.

실제 Rider 화면, Strata GPU 취소·idle 상태, 타사 플러그인의 자체 루프와 사용자 정의 비동기 slash command의 ACP 완료 표시는 이 테스트로 검증하지 않았습니다. 이 보호 장치는 OpenCode 바이너리의 전체 ACP 상태 관리 구현을 교체하지 않습니다.

## Windows 터미널 보호

`OPENCODE_ACP_TERMINAL_GUARD=1`인 새 ACP 프로세스는 실제 PowerShell shell.create.before 경로에서 명령을 UTF-8 BOM 임시 파일로 전달합니다. context 옵션의 bootstrapPath는 설치기가 관리하며 같은 패키지의 PowerShell preflight와 함께 설치합니다. tool 호출 종료 시 해당 임시 파일과 빈 전용 디렉터리만 정리합니다. Bash/cmd 등 다른 셸에는 PowerShell 문자열을 주입하지 않습니다.

bootstrap은 비종료 PowerShell 오류와 입력 프롬프트를 실패로 반환하고, 명시적인 RunAs/sudo/gsudo 요청은 AST 사전 검사로 거부합니다. 740/1223 권한 필요·승인 취소 오류는 BLOCKED_UAC로 분류합니다. OpenCode 자체의 timeout·취소·프로세스 정리를 계속 사용하며 별도의 실행 루프나 새 PowerShell 프로세스를 추가하지 않습니다. 동적 eval, 외부 프로그램의 임의 GUI 또는 OS 보안 데스크톱 전체를 제어하는 sandbox 기능은 아닙니다.
