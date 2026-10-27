# Claude Desktop Code 환경 유지보수 점검 — 2026-10-25

대상은 Claude Desktop의 **로컬 Code 화면 → OpenCodex 10100 → Strata 8080**입니다. Rider는 주 작업 환경에 포함하지 않습니다.

## 변경과 근거

1. 이전 `doctor`는 프록시 모델 목록만 검사했습니다. 목록이 캐시돼 있으면 실제 추론 서버가 내려가도 정상으로 보일 수 있어 인증된 실제 Strata `/health`의 loaded·모델 ID·컨텍스트를 추가했습니다. Desktop 3p 게이트웨이와 기본 모델 매핑, 공통 CLI 설정도 구분해 점검합니다.
2. Desktop은 일부 환경변수와 모델을 자체 주입합니다. CLI의 env를 수정한 것만으로 Desktop에 적용됐다고 판단하지 않도록 안내를 고쳤습니다. 기본 게이트웨이·모델은 기존 Desktop 3p 프로필을 보존했습니다.
3. 공통 설정 갱신을 준비·동시 변경 확인·게시·영수증 기록으로 보완했습니다. 실패 시 이미 쓴 내용과 여전히 일치하는 파일만 복구합니다. 다른 세션이 수정한 파일은 남기고 rollback_conflict로 표시합니다. 프로세스 강제 종료·전원 손실의 파일 간 원자성을 보장하는 기능은 아닙니다. 이 경우 백업과 영수증을 확인합니다.
4. `strata-maintenance` MCP는 기존 `tools/strata_mcp.py`의 stdio 처리와 기존 supervisor HTTP 제어를 재사용하는 어댑터입니다. 새 추론 서버·supervisor·에이전트 루프를 만들지 않습니다. 제공 도구는 `environment_status`, `restart_strata`, `restart_status`, `cancel_restart` 네 개입니다.
5. 재시작은 작업 체크포인트와 operation_id를 요구하고 기존 supervisor의 idle 확인과 ready 결과를 기다립니다. 취소·시간 초과·불확실한 전달은 같은 ID로 취소/영수증 확인합니다. 명확한 HTTP 거절은 같은 ID의 기존 작업을 취소하지 않도록 구분했습니다. 취소된 ready 영수증을 새 작업 재개 성공으로 처리하지 않습니다.
6. 실제 통합 시험에서 진단 timeout 1회와 조회 재시도를 확인했습니다. 이전 진단은 다른 공급자까지 포함하는 `/v1/models`를 호출했습니다. 별도 조회에서 첫 모델 목록 조회는 1.826초, 다음 조회는 0.042초였습니다. 최초 timeout의 정확한 HTTP 단계는 기록이 없어 단정할 수 없습니다. 유지보수 진단에서 불필요한 전체 목록 갱신을 제거했으며 이후 실제 후속 요청은 재시도 없이 성공했습니다. 서로 다른 전체 작업 시간을 성능 향상률로 비교하지 않습니다. 개선 후 진단 표본 3회는 62.092·43.372·46.095ms였습니다. 클라이언트의 안전한 작은 컨텍스트 제한은 허용하고 실제 서버 한도를 넘는 설정은 정상으로 판정하지 않습니다.
7. 유지보수 상세 지침은 관련 요청 때만 읽도록 연결했습니다. 소유자·정본 템플릿과 생성 프로필·루트/fork 차이·설정 백업·OpenCodex live 관리·재시작 체크포인트를 다룹니다. 프록시·Desktop 전체 종료 후 자동 재개를 보장한다고 적지 않습니다.
8. 최근 지연 표본을 CLI와 Desktop으로 나누어 보도록 `environment_status`의 기존 `/api/logs` 결과를 집계합니다. 새 요청·새 로그 조회를 추가하지 않고 마지막 12건 안에서 `claude`와 `claude-desktop`의 표본 수·성공 수·중앙 응답시간·첫 출력시간을 분리합니다. 빈 표면은 0건과 null 지연으로 표시합니다.

## 검증

- 소스 관련 검사: 최종 55개 PASS. 기존 직결 클라이언트와 공통 개발 지침 검사를 포함합니다.
- 설치본 신규 모듈 검사: 27개 PASS. 실제 Python HTTP 자식과 실제 supervisor 제어 API를 사용한 CPU 시험에서 재시작·모델 준비·같은 ID 중복 방지·다른 checkpoint 거절·busy 대기 후 취소를 검증했습니다. GPU/실제 모델 서버 재시작 증거와 구분합니다.
- 실제 Desktop 내장 CLI `2.1.308` 실행 파일과 Desktop 3p 프로필의 주소·자격 증명·기본 wire model `claude-fable-5-p035`를 메모리에서 사용했습니다. 비밀 값은 출력하거나 테스트 파일에 복사하지 않았습니다. OpenCodex를 거쳐 실제 Strata 생성이 수행됐습니다.
- 별도 Claude Code CLI 통합 점검에서 공통 사용자 MCP의 `strata-maintenance.environment_status`를 실제 호출했습니다. 3턴 후 종료 0, 전체 19.975초, API 누적 16.397초, 첫 내용 8.723초였습니다. 설정·프로젝트 파일은 변경하지 않았고 결과는 ready=true, 컨텍스트 262144였습니다. CLI stderr의 `unrecognized_model` 알림은 있었지만 도구 호출과 최종 응답은 완료됐습니다. 이는 사용자 범위 MCP를 통한 CLI 경로 증거이며 Desktop Code 화면 자체의 GUI 증거와 구분합니다.
- 초기 합산 표본 8건은 이번에 분리하니 전부 `claude` CLI였고 `claude-desktop`은 0건이었습니다. 따라서 해당 지연 값은 Desktop Code 결과가 아닙니다. 분리 후 CLI 표본 8건 중 성공 6건, 비성공 400·499 각 1건, 성공 중앙값 1,796.5ms·첫 출력 중앙값 10ms였습니다. 최신 CLI 요청은 입력 26,724토큰 중 26,025가 캐시 적중, 전체 4,144ms·첫 출력 15ms였습니다. 이는 작은 서로 다른 요청 표본이지 장기·동일 조건 벤치마크가 아닙니다.
- 분리 수정 후 소스와 설치본에서 `test_claude_opencodex_client` 및 `test_claude_maintenance` 34개가 각각 통과했습니다. 설치본 `doctor`는 ready=true·262144 문맥을 유지하고 `claude` 8건 및 `claude-desktop` 0건을 별도로 표시했습니다.
- 설치본 갱신 후 Claude Code CLI에서 유지보수 MCP `environment_status`를 실제 호출했습니다. 종료 0, 3턴, 전체 15.126초·API 11.536초·첫 내용 5.331초였고 도구 응답은 ready=true, 문맥 262144, CLI 8건·성공 6건, Desktop 0건을 반환했습니다. 호출 뒤 `doctor` 표본은 CLI 8건·성공 7건, 성공 중앙값 3,117ms·첫 출력 18ms였습니다. 최신 요청 입력 26,778 중 26,021 캐시, 완료 3,045ms·첫 출력 15ms였습니다. Claude Code 내부 전체 시간은 추론 요청과 여러 턴을 포함하므로 이 표본만으로 OpenCodex/Strata 구간이 병목이라고 하지 않습니다. 이는 CLI에서 업데이트된 MCP가 작동한 증거이며 Desktop Code GUI의 실측은 아닙니다.
- Desktop UI를 다시 관찰해 Claude 창의 접근성 트리와 화면을 함께 확인했습니다. 현재 보이는 화면은 `설정 > 일반`이고 로컬 Code 대화 화면은 아니었습니다. 탐색 도중 CUA가 사용자 입력을 감지해 추가 클릭 전에 멈췄습니다. 이번 관찰은 실제 Code 대화·MCP 호출 증거가 아닙니다.
- 첫 실제 요청 39.605초, 종료 0: 유지보수 지침 Read, 도구 검색, 실제 상태/기존 supervisor 영수증 조회, `CHECK=PASS` 작성·재확인. 상태 조회 timeout 1회와 재시도를 포함하므로 전부 무오류 PASS라고 표시하지 않습니다.
- 개선 후 같은 세션 후속 요청 14.398초, 종료 0: `CHECK=PASS-2`로 Edit·재확인. 상태와 기존 영수증을 각각 1회 조회했고 도구 오류 0개, 보호 파일 SHA-256 일치. CUA·REA·유지보수 MCP 모두 user 범위 connected입니다. 새 실제 재시작은 요청하지 않았습니다.
- Desktop Code 화면 조회는 성공했지만 창 활성화에서 `failed to activate captured window`가 발생했습니다. 이후 클릭·입력은 하지 않았습니다. 실제 GUI 세션의 생성·수정까지 검증한 결과로 확대하지 않습니다.
- OpenCodex 공급자 설정, Desktop 3p 프로필, OpenCode, Rider ACP, 기존 Claude 전용 프로필, 기존 supervisor·MCP 구현은 전후 파일 해시 일치입니다.

## 실패·재시도 기록

- 첫 CPU 23개 중 1개 기대값 실패: busy supervisor가 즉시 failed가 되기를 기대했으나 기존 구현은 최대 60초 idle을 기다립니다. 시험을 유한 timeout·실제 cancelled·프로세스 미종료 확인으로 수정했습니다. HTTP 302 예외 응답 close 누락으로 뜬 ResourceWarning도 수정했습니다.
- 한 번의 패치는 hunk 순서 때문에 적용 거절됐으며 변경 없이 순서를 바로잡아 적용했습니다.
- 설치본 전체 검사 첫 시도는 테스트가 설치하지 않은 기존 supervisor 테스트 모듈에 의존해 import 오류가 났습니다. 새 테스트의 작은 HTTP fixture를 독립시켜 설치본 시험을 완료했습니다.
- 첫 실제 요청의 보호 파일 판정 false는 시험 작성 시 Windows CRLF와 비교 시 LF 상수를 혼용한 검증 오류였습니다. 원본 bytes는 `protected fixture\r\n`이었습니다. 기록은 보존했으며 후속 시험은 실행 전후 SHA-256 비교로 확인했습니다.
- 진단 후처리 스크립트에서 `next(sorted(...))`의 TypeError가 1회 있었고 설정에는 영향이 없었습니다. 정렬된 목록 인덱스로 확인했습니다.

## 적용과 남은 범위

설치본 `tools/claude_opencodex_client.py`, 공통 사용자 유지보수 지침·MCP에 적용했습니다. 기존 공통 설정 백업은 `~/.claude/backups/strata-opencodex-20261025T122552109674Z`, 이번 설치본 helper 백업은 `C:\Users\luiny\Strata-data\backups\claude-route-surface-20261025T144609870Z`, 문서 동기화 백업은 `C:\Users\luiny\Strata-data\backups\claude-route-docs-20261025T144815938Z`입니다. 유지보수 문서 변경에 따라 공통 설정 생성기를 실행해 관리 지침 2개 파일을 갱신했고 즉시 재실행은 변경 0개였습니다. 설정 백업은 `~/.claude/backups/strata-opencodex-20261025T144827216683Z`에 있습니다. 새 진단 필드는 Desktop의 **새 로컬 Code 세션**이 로드해야 사용할 수 있습니다.

실제 Strata 모델 서버·OpenCodex·Desktop 재시작/업데이트 및 그 후 GUI 대화 복구, 262K 장문 압축, 장시간 무인 운영, 다른 PC/운영체제는 이번에 실행하지 않았습니다. 프록시나 Desktop을 재시작할 때는 기존 소유자와 저장한 체크포인트를 사용하며, 확인되지 않은 자동 복구를 약속하지 않습니다. 커밋·푸시는 하지 않았습니다.

근거: [Desktop 공통 설정·MCP 범위](https://code.claude.com/docs/en/desktop#shared-configuration), [Desktop 자체 환경변수](https://code.claude.com/docs/en/desktop#environment-variables-desktop-sets-itself).

진단 원본: `C:\Users\luiny\Strata-data\diagnostics\claude-self-maintenance-20261025`.
