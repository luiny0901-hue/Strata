# 중지 검증 (2026-10-21)

ACP guard가 셸·하위 에이전트를 실행하기 직전에 AbortSignal을 확인하도록 보완했다. 이미 취소된 요청의 대기 도구를 새로 실행하지 않는다. 코어의 실행 중 취소를 별도 루프나 전역 프로세스 종료로 대체하지 않는다.

검증:

- Node guard 검사: 이미 취소된 shell/subagent 실행 횟수 0.
- 출력 복구 자동 검사 17개: 소비자 취소가 upstream cancel에 전달되고, 미완성 도구 복구 재시도·완료 콜백은 호출되지 않음.
- 설치된 OpenCode 2.0.22 격리 ACP + 모의 모델: 생성 중 취소 약 0.065초, 모의 서버 연결 종료 확인, 부분 쓰기 미실행, 같은 세션 새 요청 성공.
- 실행 중 셸 취소: 남은 쓰기 미실행, 늦은 자동 재개 모델 HTTP 도달 차단, 새 요청 성공.
- 하위 에이전트 셸 취소 및 새 요청 성공.
- ACP stdin EOF: 소유 프로세스 종료, 남은 쓰기 미실행.

증거: diagnostics/cancel-hardening-0-20261021부터 cancel-hardening-3-20261021까지. events.json, requests.json, rpc-timings.json, stderr.log 보존.

Rider 실제 중지 버튼·OpenCode TUI 키 입력·실제 Strata 엔진 취소·GPU idle은 미검증이다. HTTP 연결 종료만으로 엔진이 멈췄다고 판단하지 않는다. 실제 엔진 검증은 해당 요청/슬롯 취소 로그, /slots 또는 /status idle과 같은 세션 후속 요청까지 확인해야 한다. 이미 완료된 파일 저장·MCP 입력·외부 설치의 부작용은 취소로 롤백되지 않으며 타사 프로세스가 취소를 지원하지 않을 수 있다.
