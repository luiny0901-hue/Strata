# 장기 에이전트 지연·취소 보완 (2026-10-24 KST)

## 실행 상태
Rider 재실행 후 ACP wrapper cb641603... 사용을 확인했다. 기존 모델/GPU/High 추론 강도/압축 임계점/단계 제한은 변경하지 않았다.

## 변경
- 선택형 localTitles=true: 사용자 요청의 첫 줄을 최대60 Unicode 문자로 제한해 대화 제목을 로컬에서 만든다. 제목용 LLM 호출을 없앤다. 에이전트 답변·코드·최종 보고서에는 이 길이 제한을 적용하지 않는다.
- 선택형 taskStreamCancellation=true: ACP transport가 관리하는 작업 UUID와 모델 응답 스트림을 연결한다. 완료·취소·연결 종료 후 응답 바이트 전달을 중단하고 상류 reader를 취소한다. task state 감시는 활성 스트림에만 존재하고 EOF/실패/취소 시 해제한다.
- ACP cancel이 core에 전달될 시간을35ms 허용하되 그 사이 새 응답 바이트를 전달하지 않는다. 파일 감시와1초 owner watchdog를 사용한다. 정상 스트림에는 인위적 지연이 없다.
- 새 설치기 asset hash에 task-stream.mjs를 포함하고, 원격 클라이언트 revision10에서 위 옵션을 함께 선택한다. 일반 플러그인 기본값은 꺼짐이며 기존 미선택 경로는 유지한다.

## 실패 및 검증 이력
1. long-agent-cancel-baseline-20261024-a: installed OpenCode2.0.22+모의 모델, 첫 내용 전 취소 후5초 내 상류 연결 종료 미확인(실패).
2. long-agent-cancel-bridge-20261024-a: 초기 응답 스트림 연결로 모의 모델 검사 통과(약0.072초).
3. long-agent-live-cancel-20261024-a: 실제 Strata 첫 요청은 취소됐으나 별도 요청이 슬롯을 차지해45초 내 idle 복귀 실패. 추가 호출을 추적했다.
4. long-agent-cancel-bridge-20261024-b 및 live-cancel-b: 요청 전 차단/재시도 차단을 추가한 시도는 provider.transport 오류를 반환해 실패. 이 사전 차단 코드는 최종 구현에서 제거했다. live b의 HTTP audit에서 title과primary 호출이 각각 존재함을 확인했다.
5. 최종 localTitles+stream cancellation: long-agent-cancel-bridge-20261024-c 모의 검사 통과(약0.019초).
6. long-agent-live-cancel-20261024-c 실제 검증 통과. 약119414토큰 입력의 첫 내용 전 취소: ACP cancelled 약0.021초, 엔진 취소 로그·슬롯idle 복귀 약9.670초. GPU는 실행 중 프리필 조각을 마친 뒤 멈췄다. 동일 ACP 세션에서 FOLLOWUP_OK 생성과 최종idle 확인. HTTP audit는 primary2회(원요청·명시 후속 요청)만 존재하며 title 호출은 없다.

원시 기록은 C:/Users/luiny/Strata-data/diagnostics/ 각 위 폴더에 보존했다. 실제 모델 연결은 기존 실행 중 Strata API이며 서버/엔진을 재시작하지 않았다. GUI·셸·CUA 도구를 테스트 모델에 제공하지 않았다. 이전 실패를 최종 성공으로 대체하지 않는다.

## 회귀 검사
- Node32개 통과: 스트림 수명5개, 출력 복구22개, MCP 준비5개.
- ACP guard6개 검사 그룹 통과: 미선택 경로, 취소 후 도구 실행 차단, 유한 대기, 후속 요청, 지침 중복 방지.
- Python11개 통과: 설정 이전5개, 설치1개, 전송5개.
- long-agent-compact-bridge-20261024-a: installed OpenCode+모의 사용량262144 예산의 자동압축·후속수정 통과. 실제262k 요약 추론 속도는 아니다.
- long-agent-steps-bridge-20261024-a: installed OpenCode+모의 모델의210순차 저장,211모델 호출,512단계 예산 내 완료 통과. 복잡한 코딩 품질 증거가 아니다.
- long-agent-reconnect-bridge-20261024-a: 새 스트림 보완과 출력 복구를 함께 켠 installed OpenCode 모의 검사 통과. ACP를 재실행해 기존 세션을 불러올 때 완료 작업이 재실행되지 않고 명시적인 후속 요청만 실행됨을 확인했다.

## 적용과 한계
현재 설정과runtime source를 백업 후 반영했다. 2026-10-24 08:47:20 KST Rider OpenCode 로그에서1487afb1... 새 플러그인과task-stream.mjs 재로딩을 확인했다. 현재 연결의 새 플러그인 로딩 증거이며 실제 Rider 중지 버튼 조작을 재현한 것은 아니다. 실행 중 서버 및 Rider를 강제 재시작하지 않았다.

기존 설정 백업과 비교해 변경된 최상위 항목은 plugins 하나였다. 모델·High·압축·권한 설정은 보존했다. 배포용 일반 ZIP과 개인 프로필 ZIP에도 새 모듈과 revision 10 설치기를 반영한다. 개인 프로필은 개인 ZIP에만 유지하며 기존 ZIP은 별도 백업한다.

실제 GPU 취소 시험은1회 성공이다. HTTP 헤더 이전에 멈춘 서버, 별도 ACP 요청으로 소유되지 않는 하위 세션, WebSocket 경로, 장시간 GUI, 다중 사용자, 실제262k 압축 품질의 모든 경우를 보장하지 않는다. 필수 질문·권한 승인 대기는 자동 승인하지 않는다. 실제 압축 비용을 줄이기 위해 High나keep/buffer를 임의 축소하지 않았다.
