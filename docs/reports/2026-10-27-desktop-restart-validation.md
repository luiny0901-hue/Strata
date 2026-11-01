# Desktop 재시작 실동 검증 체크포인트 (2026-10-27, 검증 종료)

범위: 현재 경로(Claude Desktop Code + OpenCodex + Strata)의 무인·재시작 시나리오 재검증. 사용자 위임으로 진행.

최종 결과: 5차 인계(-e)에서 접수→조용한 첫 순간 종료→네이티브 재개 1회→수락→자동 재열기→`ready`(handoff_completed=true, 재열기 사용자 확인) 전 구간이 사람 동작 없이 완주했다. 요청한 "고정 창 만료 대신 조용한 첫 순간에 바로 재시동"(e4b563d4)은 -d·-e에서 실동 확인. 관찰 전문은 `docs/CLAUDE_DESKTOP_RESTART_20261027_KO.md`의 날짜별 항목에 있다.

구조 확인(2026-10-27 부모 체인): supervisor·모델 서버는 explorer에 걸린 별도 트리로 Desktop과 독립이다(Desktop이 끝나도 서버는 남고, 재열기로 열린 Desktop이 오히려 supervisor의 자식이었다). 재실행 경로는 모델 서버=`restart_strata`, Desktop=체크포인트 인계(`restart_desktop`), supervisor=실행기 재시작이며, 에이전트가 supervisor를 띄울 때 Desktop Code 도구 자식 트리 안에서 실행하면 Desktop 종료 연쇄에 죽는 문제를 확인해 분리 실행 규칙(`Win32_Process.Create` 등)을 `docs/CLAUDE_SELF_MAINTENANCE_KO.md`에 기록했다.

완료 커밋: 977b569b(잔재 정리), 418d6c26(만료 세션·error_code), e4b563d4(대기 상한 제거), d1e025fa·b1e8a36d·b67e2ef0·73d0944d·ad6451f1 및 이후 문서 커밋. 남은 작업 없음. 푸시는 미승인 상태다.
