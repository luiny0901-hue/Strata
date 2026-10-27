# Desktop 재시작 실동 검증 체크포인트 (2026-10-27, 4차 제출 준비)

범위: 현재 경로(Claude Desktop Code + OpenCodex + Strata)의 무인·재시작 시나리오 재검증. 사용자 위임으로 진행.

완료: OpenCode/Rider 잔재 정리·커밋(977b569b). 인계 3건(-a/-b/-c) 관찰 종료(모두 부작용 없는 안전한 만료). 수정 저장: 만료 세션 유휴 처리·고정 error_code(418d6c26), 인계 대기 180초 상한 제거로 거래 기한(기본 24시간)까지 대기 후 조용한 첫 순간에 종료(e4b563d4), 로드 경계 문서화(d1e025fa). 데스크톱 테스트 76개 통과. `tools/claude_desktop_runtime.py`는 운영 루트 `C:\Users\luiny\Strata\tools\`에 백업(`.before-wait-cap-20261027-213758.bak`) 후 배포·해시 일치. `restart_strata`(strata-code-reload-20261027-wait-cap-1) ready.

전제: 인계 오너는 supervisor 프로세스 시작 시 코드를 읽으므로(현재 supervisor는 02:37 시작 프로세스), 실동 확인 전 사용자가 평소 ON/OFF BAT로 supervisor를 재시작해야 한다. 확인 명령: 8768 포트 리스너 프로세스의 시작 시각이 배포 시각(21:36) 이후이면 새 코드가 로드된 것.

남은 작업(사용자 승인: 재시작 후 실동 확인용 인계 제출): supervisor 재시작 확인 후 `desktop_restart_status`로 enabled·current_session_id 확인, `restart_desktop(operation_id="strata-desktop-restart-recheck-20261027-d", session_id=<확인 ID>, checkpoint_path=<이 파일 경로>)`를 1회만 제출하고 해당 턴을 종료한다. 이후 거래 영수증이 waiting_for_handoff→quitting→continuing→ready로 진행되는지, 재시동이 조용한 첫 순간에 곧바로 걸리는지 관찰한다. 복귀 세션에서 이 체크포인트와 실제 파일을 대조한 뒤 acknowledge_desktop_restart에 operation_id·nonce·현재 네이티브 session_id를 전달한다. 최종 결과를 사용자에게 한국어로 보고한다.

금지: 같은 작업의 중복 재시작 제출(실패는 자동 재시도 없음), 프로세스 강제 종료, 확인 없는 복구 계속, 푸시(미승인).
