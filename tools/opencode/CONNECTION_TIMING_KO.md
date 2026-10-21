# Strata / OpenCode / MCP / Rider 연결 점검 (2026-10-21)

현재 관측: OpenCode 프로세스 존재, Rider 프로세스 미확인, 선택된 Strata endpoint의 /health 연결 실패(약 2064ms). 서버·IDE를 시작하거나 재시작하지 않았다. 따라서 전체 운영 경로의 병목 판정은 미완료다.

실제 설정된 로컬 MCP에 initialize 및 tools/list만 요청했다. 앱 조작·REA 분석·모델 추론은 요청하지 않았다.

| 서버 | initialize | tools/list | 도구 수 | JSON 크기 |
|---|---:|---:|---:|---:|
| cua-driver | 343.17ms | 1.73ms | 17 | 83060 bytes |
| rea (기존 npx 명령) | 2534.03ms | 473.94ms | 207 | 3423816 bytes |

REA 캐시 경로 직접 Node 실행 단회 비교: initialize 1571.57ms, catalog 445.68ms. 단회 실행·OS 캐시 영향이 있으므로 차이를 반복 통계로 보지 않는다. 캐시 절대경로 고정은 재설치·캐시 삭제 시 깨질 수 있어 운영 설정에 적용하지 않았다. 카탈로그 크기는 초기 수신 JSON이며 모든 도구 스키마가 매 모델 요청에 들어간다는 증거가 아니다. 기존 REA 전용 subagent와 기본 Code Mode 설정을 유지했다.

격리 OpenCode + 모의 모델 ACP: initialize 373.49ms, session/new 330.79ms, 출력 제한 복구·파일 저장·최종 응답을 포함한 session/prompt 147.43ms. Rider 화면이나 Strata 추론 지연은 포함하지 않는다.

증거: diagnostics/mcp-startup-20261021-1.json 및 diagnostics/chain-acp-timing-20261021/rpc-timings.json. 측정 도구는 tools/measure_mcp_startup.py이고, 기존 ACP 시험에도 RPC별 시간을 저장하도록 보완했다. 진단 도구 stderr는 저장하지 않고 배출해 불필요한 메모리 누적을 피한다.

서버와 Rider가 사용 가능한 상태에서 같은 세션의 요청 시작·첫 토큰·도구 결과·ACP 종료·화면 표시 시각을 대조해야 모델/네트워크/클라이언트 중 실제 반복 병목을 판단할 수 있다. 이번 결과만으로 실제 운영 경로가 빠르거나 문제가 없다고 주장하지 않는다.
