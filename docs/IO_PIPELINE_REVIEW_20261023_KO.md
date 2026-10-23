# 2026-10-23 읽기·쓰기·MCP·ACP 경로 측정

## 범위와 조건

실제 CUA MCP 메타데이터, PowerShell 실행기, 격리 파일 I/O, 설치 OpenCode+실제 Strata, 합성 ACP 표시 스트림을 구분했다. 실제 Rider는 창이 열려 있지 않아 computer-use list_apps에서 isRunning=false/windows=[]를 확인했으며 실행·포커스·사용자 입력 조작 없이 GUI 측정을 보류했다.

## 파일 입출력

OS 캐시를 비우지 않은 읽기다. 저장은 같은 폴더 임시 파일에 write/flush/fsync 후 replace하고 SHA256으로 확인했다. 원시 SSD 최대 대역폭·물리 장치 캐시·전원 손실 안전성의 증거는 아니다. 각 크기5회, 합계45개 검사 통과.

| 파일 크기 | 전체 읽기 중앙값 | 1KiB 구간 읽기 | 원자적 저장+fsync |
|---|---:|---:|---:|
| 8192B | 0.089ms | 0.079ms | 1.486ms |
| 1048576B | 0.375ms | 0.092ms | 1.942ms |
| 16777216B | 5.182ms | 0.101ms | 12.810ms |

## 도구 실행·메타데이터

- 독립 읽기4개, 교차 순서5쌍, 같은 내용 검증 통과.
- 개별 셸 중앙값1.110s → 묶음0.282s (74.60% 감소). 이미 설치된 묶음 조회 지침을 유지.
- CUA MCP 시작부터 initialize 완료 중앙값0.382s. GUI 도구 호출은 하지 않음.
- tools/list 9회 중앙값1.812ms, 도구17개. 이 메타데이터 경로를 줄이기 위한 추가 캐시/도구 숨김을 적용할 근거 없음.

## 실제 OpenCode+Strata 읽기/수정

이 시험에만 None 추론을 지정했다. 전역 추론 수준을 변경하지 않았다. 격리 HOME/DB/프로젝트에서 read/edit/write만 모델에 노출했다. MCP·셸·GUI 도구는 제공하지 않았다. 원본 프로젝트를 바꾸지 않았다.

| 실행 | 첫 읽기·저장·재확인 | 후속 수정·재확인 | 결과 |
|---|---:|---:|---|
| live-acp-a | 5.798s | 2.002s | PASS |
| live-acp-direct-b | 6.222s | 2.017s | PASS |
| live-acp-compact-b | 5.278s | 2.099s | PASS |

첫 세션은 파일·종료 상태와 관련 없는256파일을 확인했다. 보강한 후속2세션은 입력2파일도 보존하고 read 호출3/2개 및 각 턴의 일반 답변 전달을 추가 검증했다. 모두 TOTAL=42→TOTAL=43, end_turn, 최종 보고 전달이 확인됐다. 필터 유무 표본이 적고 모델 생성은 같지 않아 전체 시간 차이를 필터의 인과적 속도 향상률로 해석하지 않는다.
첫 세션의 도구 in_progress→completed 클라이언트 도착 간격은 중앙값23.069ms이며 디스크 시간 자체와 구분한다.

## 긴 코드 출력·부분 수정

- 250함수 중1개 수정, 각 방식2회 교차 순서. 전체 재작성 중앙값23.040s → 부분 수정2.500s (89.15% 감소).
- 전체 출력3667토큰·디코딩 약20.7~20.9초, 부분 출력64토큰. AST로 다른249함수 보존 확인. 실제 복잡한 새 프로그램 설계의 속도/품질 보장은 아니다.

## 표시 스트림 부하

생각 알림5000개+긴 완료 보고서+승인 요청+도구 상태+최종 응답의 합성 스트림. 각 방식3회 교차 순서.

- direct: 중앙값0.098s, 전달4174388B, 바이트 단위 기대 결과 모두 일치.
- compact: 중앙값0.210s, 전달104388B, 바이트 단위 기대 결과 모두 일치.
- 생각 필터는 전달량을 약97.5% 줄였지만 파싱·추가 프로세스 비용이 있다. 실제 Rider 화면 렌더링 시간 개선으로 주장하지 않는다.
- 보고서/승인/도구 결과를 숨기거나 출력 버퍼를 늘려 완료 보고를 늦추는 변경은 하지 않았다.

## 변경과 회귀 검사

- 측정 도구3개 추가 및 기존 도구1개 확장: benchmark_local_io.py, benchmark_live_acp_io.py, benchmark_acp_display.py 및 기존 코드 fixture의 51~250함수 옵션.
- 부분 읽기·독립 조회 묶음·부분 수정·추론 단계 캐시 보존·생각 표시 필터는 기존 적용을 유지. 추가 디스크/모델/런타임 전역 튜닝은 적용하지 않았다.
- Python 기존 fixture2개, 표시 프로토콜1개, Node 작업 지침3개 모두 통과. 실제 읽기·쓰기 과제와 모든 비교 검사는 통과했으며 모델 오류·실패 후 재시도는 없었다.
- Rider GUI·REA 실제 바이너리 분석·macOS·원격망 지연·다중 사용자 동시 부하·디스크 cold-cache는 미검증. 푸시하지 않았다.

## 증거

- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-files-a
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-terminal-a
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-mcp-a
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-live-acp-a
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-live-acp-direct-b
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-live-acp-compact-b
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-code250-a
- C:\Users\luiny\Strata-data\diagnostics\io-paths-20261023-display-a
