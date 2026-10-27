# Claude Desktop 재시작 후 작업 재개 검증

2026-10-27, 현재 Windows PC의 Claude Desktop Code → OpenCodex 10100 → Strata 8080 경로에서 확인했다. 최종 시험 C는 체크포인트 저장부터 정상 종료, 같은 네이티브 대화의 작업 재개, 결과 검증, 원래 Desktop 대화 복귀까지 통과했다. 장시간·다른 PC·모든 권한 모드의 검증으로 확대하지 않는다.

## 적용한 동작

- 기존 Strata supervisor가 Desktop 밖에서 인계를 소유한다. 별도 상주 코딩 루프나 두 번째 모델 서버를 만들지 않는다.
- 작업 에이전트가 프로젝트 안에 완료·미완료·검증을 기록하고 `restart_desktop`을 한 번 제출한다. 원래 도구 결과와 최종 턴 종료가 기록된 뒤에만 정상 종료한다.
- PID·프로세스 생성 시각·실행 파일·소유 사용자를 대조하고 Windows Restart Manager의 정상 종료만 사용한다. 다른 Desktop Code 세션이 작업 중이면 종료하지 않는다.
- Desktop을 닫은 동안, 해당 Desktop에 설치된 같은 네이티브 Claude Code를 `--resume --print`로 한 번 실행한다. 원래 대화 UUID, Strata 모델 경로, 추론 성능, 권한 모드를 보존한다. 작업 상태 확인과 정확한 인계 확인 응답이 있어야 성공으로 판정한다.
- 복구 실행이 끝나면 원래 Desktop 대화를 다시 연다. 현재 3p 프로필은 OS의 대화 복귀 링크를 무시하므로, 기존 CUA의 백그라운드 접근성 버튼으로 복귀한다. 제목이 정확히 일치하는 버튼이 하나일 때만 한 번 선택하고 원래 UUID의 포커스 변경을 확인한다. 물리 마우스·키보드, 전경 입력, 좌표 추측을 사용하지 않는다.
- 원래 MCP 연결 종료는 인계 취소가 아니다. 사용자의 명시적 중지는 별도로 전달한다. 같은 operation ID는 재실행하지 않고 기존 영수증을 반환한다. 불확실한 종료·저장 실패·기한 초과·중복 제목·불완전한 화면은 확인 필요 상태로 남긴다. 복구 중 원래 대화를 사용자가 다시 열면 임시 작성자를 중지한다.

새 Desktop 대화는 UUID를 실행 인자에 넣지 않았다. 기존 SessionStart 훅의 실제 UUID를 프로세스 생성 시각과 묶는 연결 기록을 추가해 최근 대화 추측을 없앴다. CUA의 접근성 결과는 레이아웃 노드를 생략해 `elements_complete=false`일 수 있었다. 버튼 선택 전에 `truncated=false`, 남은 노드 0, 반환·전체 요소 수 일치라는 실제 순회 완료 근거를 함께 확인한다.

## 실제 시험 이력

| 시험 | 관측 | 판정 |
|---|---|---|
| A | 새 Desktop 대화에서 UUID가 실행 인자에 없어서 상태 도구가 식별하지 못했다. 파일 변경·재시작 요청 없이 중지했다. | 실패를 보존하고 훅 연결로 수정 |
| 정상 종료 단독 | 설치된 Desktop 3.6556.2.0의 검증된 주 프로세스를 Restart Manager로 정상 종료했다. 강제 종료 없음. | 통과 |
| B | 체크포인트 저장, 정상 종료, 동일 UUID 재개, 인계 확인, 결과 파일 작성·바이트 검증에 성공했다. 앱은 열렸으나 대화 복귀 링크가 무시되어 새 세션 화면에 남았다. | 기존 영수증은 `needs_attention / reopen_failed`로 보존 |
| CUA 복귀 첫 준비 | 접근성의 `elements_complete=false`를 지나치게 엄격하게 해석해 클릭 전에 중지했다. 읽기 전용 재검사에서 순회 완료·레이아웃 생략을 확인했다. | 판정 조건 수정 |
| CUA 복귀 보완 시험 | 백그라운드 접근성 클릭 1회, 실제 원래 대화 포커스 변경과 복구 보고 표시를 확인했다. | 통과, B 영수증을 소급 변경하지 않음 |
| C, `desktop-live-20261027-c` | 전체 흐름을 별도 폴더에서 다시 실행했다. 영수증 `ready`, `acknowledged=true`, `handoff_completed=true`, 복구 CLI exit 0·success, 취소 없음. | 통과 |

최종 C의 `result.txt`는 정확히 `DESKTOP-RESUME-OK=29`와 LF 하나, 총 21바이트였다. 원본 `source.txt`는 시험 전 SHA-256과 일치했다. 결과 파일이 없다는 체크포인트 대조 후 인계 확인과 결과 작성이 이어졌으며, 실제 도구 호출 ID로 중복을 제거했을 때 C의 재시작 호출은 1회였다. SDK가 재개 시 기록한 이전 대화 재전송을 도구 재실행으로 세지 않았다. 최종 Desktop 화면에서도 같은 대화의 C 완료 보고와 입력 가능한 유휴 상태를 확인했다. 임시 복구 CLI는 남아 있지 않았다.

원래 Desktop ID는 `local_a0543552-b3a7-4a91-abdb-a3bc5189cd3e`, 네이티브 UUID는 `01b59933-6a59-4fb1-820d-8ac499af29fd`였다. 완료 후에도 동일한 값이었다. 모델 경로는 `strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`, High·bypassPermissions였다. 기존 권한 모드를 보존한 시험이며 다른 모드도 통과했다고 주장하지 않는다.

준비 중 관리 프로세스를 세 차례 정상 재실행했다. 첫 사전 점검은 원시 상태 API에 없는 정규화 필드를 기대해 신호 전송 전에 중지했으며 실제 필드로 수정했다. 모델 로딩 중 Desktop을 열었던 한 차례에는 일시적인 Gateway 오류가 표시됐고, 모델 준비 후 정상 확인됐다. 이후 전체 시험 C는 모델 준비 후 시작했다. 관리 프로세스 교체 뒤 Desktop이 닫힌 경우도 정상 재실행하고 보존된 시험 대화를 다시 열어 준비했다. 이 준비 이력을 최종 C의 자동 복귀 성공과 구분한다.

## 코드 검사

최종 명령은 프로젝트 Python에서 다음 8개 unittest 모듈을 실행했다.

```text
python -X utf8 -m unittest tools.test_claude_desktop_restore tools.test_claude_desktop_runtime tools.test_claude_desktop_restart tools.test_claude_desktop_bridge tools.test_claude_maintenance tools.test_claude_opencodex_client tools.test_claude_code_guidance tools.test_strata_server_supervisor
Ran 201 tests in 44.690s — OK (skipped=1)
```

200개 통과, 심볼릭 링크 생성 권한이 필요한 검사 1개 제외다. 이 검사는 CPU·모의 계약·소유한 시험 자식 프로세스 검사이며 실제 모델 검증과 구분한다. 대상 BAT·supervisor·시작 안내의 `git diff --check`도 통과했다. Git의 LF/CRLF 안내는 별도로 출력됐다.

중간 실패도 보존했다. 초기 런타임 fixture 검사 28개에서 11개 assertion 실패가 있어 수락 판정·원래 프로세스 소유·취소/기한·출력 경계를 보강했다. 설정 소유 영수증을 추가한 뒤에는 fixture도 새 계약으로 수정했다. 초기 통합 163개 검사에서 시험 자식 시작이 10초를 넘긴 1개 오류가 있었고, 같은 단독 검사는 0.120초에 통과했다. 이후 191개 통합 검사가 통과했다. 추가한 재개 중 수동 복귀 검사에서는 테스트의 `time` import 누락으로 195개 중 1개 오류가 발생해 수정했으며, 수정 후 195개·200개·최종 201개 검사가 통과했다. 실패 결과를 성공 결과로 덮어 해석하지 않았다.

## 현재 적용 위치와 근거

소스는 `C:\Users\luiny\Strata-opencode-session-recovery`다. 실제 운영 루트 `C:\Users\luiny\Strata`에는 변경된 supervisor와 Desktop 런타임·컨트롤러를 백업 후 배포하고 ON/OFF BAT의 관리 실행 인자만 추가했다. 기존 `PYTHONPATH`, NVFP4 effort 패치, 모델·Pack·GPU 프로필은 보존했다. 복귀 보조기는 설정에 기록된 현재 소스 경로에서 실행하며 기존에 등록된 정책 적용 CUA 서버를 사용한다.

선택 설정은 `~/.config/strata/server-control/desktop-restart.json`, 읽기 전용 상태 허용 규칙과 SessionStart 훅은 기존 Claude 소유 설정에 병합했다. 변경된 사용자 전역 `CLAUDE.md`는 덮어쓰지 않았다. 설정·지침·운영 파일의 백업 영수증은 `~/.claude/backups/strata-opencodex-*`에 있다. 소스 경로를 이동하거나 작업 트리를 보관하기 전에는 설정의 `client_root`, 훅·MCP 소스 경로를 함께 갱신해야 한다.

검증 파일은 `C:\Users\luiny\Strata-data\diagnostics\desktop-restart-20261027`에 있다. `live-c-verification.json`, `final-health.json`, `unique-live-tool-calls.json`, `cpu-final-201-tests.log`, 운영 배포 diff·백업 영수증, 이전 실패 관측을 보존했다. B의 처음 원본 바이트 비교는 Windows `write_text`가 만든 CRLF를 LF로 기대해 false였으며, 파일 변경 오류가 아니었다. C는 시험 전 원본 해시를 저장해 이 모호함을 없앴다.

REA로 설치된 Desktop의 선택된 ASAR 파일을 정적으로 확인했다. 근거 ID는 `ev_bc2a1b4da61ca9a1e1e43c501d20c9d8ce3f9a0fa305a2a79d44e19a9c2dcfe1`이다. 원본 ASAR SHA-256은 `3e9cb8e8034e75d9e1996f960169877c556e17a454041a25233b372493fec9ac`다. 처음 무결성 중단 시도와 이후 기록 후 계속한 결과를 둘 다 보존했으며, 선택하지 않은 파일과 native 리소스 무결성 불일치를 검증 완료로 승격하지 않았다. 대상 JavaScript를 실행하거나 설치 파일을 수정하지 않았다. 복귀 링크 무시는 실제 `main.log`의 `code entry deep link ignored (entry points off)`와도 대조했다.

기반 API는 [Windows Restart Manager 정상 종료](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmshutdown), 설치된 CLI help와 [Claude Code CLI](https://code.claude.com/docs/en/cli-reference), [세션 재개](https://code.claude.com/docs/en/sessions)를 참고했다. 정적 API 존재만으로 성공을 판단하지 않고 위 실제 C 시험으로 확인했다.

## 범위와 사용

[유지보수 안내](CLAUDE_SELF_MAINTENANCE_KO.md)의 체크포인트·접수·턴 종료 순서를 따른다. 새 PC는 공통 Claude 설정을 먼저 적용한 다음 `setup-desktop-restart.bat`로 선택 기능을 켜고 기존 Strata 관리 실행기를 다시 시작한다. 이번 PC에는 이미 적용했다.

현재 검증은 같은 Windows PC·같은 사용자·설치된 Desktop/CLI와 기존 CUA 구성에 한정된다. RTX 3090 Ti 단일 모델 GPU, 서버 컨텍스트 262,144, 동시성 1이 유지됐고 최종 연결·모델 준비·Strata 슬롯 유휴를 확인했다. 이번 재개 입력은 약 49K였으며 262K 경계·자동 압축·24시간 운영·원격 PC·macOS·Linux·다른 모델·권한 모드·중복 제목의 실제 GUI 실행을 검증한 결과는 아니다. CPU 모의 검사의 취소·오류·중복 방어를 모든 실환경의 보장으로 표현하지 않는다. `ready`는 이 인계의 완료이며 사용자 프로젝트 전체 완료를 뜻하지 않는다.

기존 미커밋 작업을 보존했으며 이 변경을 커밋하거나 푸시하지 않았다.

## 2026-10-27 인계 대기 실패 관측과 수정

실전 제출 두 건(`-a`, `-b`)이 모두 실제 종료 이전 `waiting_for_handoff`에서 180초 만료로 `handoff_failed`됐다. 데스크톱·세션·체크포인트에는 영향이 없었다. 원인은 실트랜스크립트로 확인했다. 같은 프로젝트에 남은 중단 세션 하나가 마지막 기록 63분 전에 마지막 줄이 종료 전 도구 호출인 채 `busy`로 남아, 대기 조건(원 턴 종료 + 다른 소유 세션 유휴)이 계속 성립하지 않았다.

수정 두 가지. 첫째, 소유 세션 중 트랜스크립트 기록이 15분(`STALE_OTHER_SESSION_SECONDS`) 이상 없는 것은 중단·대기로 보아 유휴로 본다. 둘째, 대기 시간 초과 시 원인을 고정 공개 코드로 구분해 거래에 남긴다(`original_turn_unfinished` 또는 `other_sessions_busy`). 개인 본문은 거래에 남기지 않는다. 관련 데스크톱 테스트 61개 통과를 확인했고, 운영 루트에는 백업 후 배포했다. 실제 종료·복귀 구간은 수정 이후 제출로 다시 확인한다.
