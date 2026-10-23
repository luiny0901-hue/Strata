# 2026-10-23 컨텍스트·출력 부하 재측정

## 조건

실제 Strata IQ4_XS API를 순차 호출, temperature=0, 시험별 None/High 지정. 서버 한도262144, 초기 구현 실제 입력259630, High 장문257469. 출력·수정 여유를 남겼다. 서버 설정·모델·추론 기본값 변경 없음. 부하 중 RTX3090Ti 사용을 단일 nvidia-smi 표본으로 확인했으며 평균 전력·장시간 안정성 시험은 아니다.

직접 API 합성 로그·함수/100함수 파일 시험이다. Rider GUI 시간, 다중 사용자 큐, 외부 네트워크, 실제 대규모 프로젝트 품질과 구분한다. cached_tokens=0인 요청을 cold로 분류했다.

## 구현과 같은 대화의 수정

| 단계 | 전체 시간 | 함수 검사 |
|---|---:|---:|
| 1 | 90.008s | 5/5 |
| 2 | 2.049s | 6/6 |
| 3 | 2.346s | 7/7 |

첫 요청 프리필88.162s, 2944.9tok/s. 후속 수정 첫 호출의 새 프리필은45/66토큰.

## SSE 첫 답변

| 추론 | 입력 토큰 | 첫 요청 | 동일 입력 재사용 |
|---|---:|---:|---:|
| none | 8178 | 3.176s | 0.060–0.069s |
| none | 65467 | 21.442s | 0.084–0.086s |
| none | 259445 | 87.780s | 0.155–0.156s |
| high | 8214 | 4.723s | 1.383–1.383s |
| high | 257469 | 90.926s | 1.471–1.471s |

High 지연에는 내부 추론 생성이 포함된다. High 재사용은 각 길이1회이며 안정적인 우위를 주장하지 않는다. 10토큰 정답의 tok/s를 디코딩 안정성 지표로 쓰지 않는다.

## 대안 비교

| 시험 | 시간 | 결과 |
|---|---:|---|
| context-full-cold | 88.801s | True |
| context-full-warm | 0.546s | True |
| context-prefix-changed | 88.164s | True |
| context-selected-1 | 0.652s | True |
| context-selected-2 | 0.582s | True |
| edit-full-1 | 9.938s | True |
| edit-patch-1 | 2.467s | True |
| edit-patch-2 | 2.327s | True |
| edit-full-2 | 9.819s | True |

한 함수 수정: 전체 재작성 중앙값9.878s, 부분 수정2.397s, 시간75.74% 감소. 각각2회 교차 순서, 출력1417/64토큰, AST로 다른99함수 보존 확인. 일반 프로젝트 전체 향상률은 아니다.
근거 선택은 시험기가 알고 있는 CONTRACT 레코드를 추린 통제 조건이다. 자동 검색·누락 내성·실제 코드 의존성 선택을 검증하지 않았다.

## ACP·CPU 검사와 실패 이력

- ACP-a: 모듈 실행 import 오류로 시험 전 실패. 상대 import 지원을 수정.
- ACP-b: 압축·후속 수정·2048파일 보존 통과 후 예전 정책 문구를 고정한 assertion 실패. 원본 정책 상수를 읽도록 수정.
- ACP-c: 설치 OpenCode에서 동일 시나리오 통과. 한도262144·사용량220000은 mock 모델 값이며 실제 모델 압축 품질이나 Rider GUI 검증이 아니다.
- 표시 래퍼 CPU1개 통과: 생각만 제거하고 일반 한국어 보고·도구 상태·완료·취소/승인 입력·종료코드 보존.
- Node 작업 지침3개 통과.

## 판단과 변경

큰 비용은 cold 프리필과 앞부분 변경에 따른 캐시 손실이다. 기존의 관련 구간 읽기·고정 앞부분 보존·후속 메시지 추가·부분 수정 정책을 유지한다. 임의 모델/엔진 튜닝이나 추론 수준 축소, 컨텍스트/압축 설정 변경은 하지 않았다.
측정기의 targets/samples/effort/max-output 옵션, ACP 검사기의 import·고정문구 오류를 수정했다. 새 엔진 최적화 이득은 입증하지 못했으며 푸시하지 않았다.

## 증거 경로

- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-edits-a
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-sse-a
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-high-a
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-ab-a
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-acp-a
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-acp-b
- C:\Users\luiny\Strata-data\diagnostics\context-load-20261023-acp-c
