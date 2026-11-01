# 2026-10-23 추론 단계별 측정과 전환 캐시 개선

## 범위와 조건

- 실제 실행 중인 Strata IQ4_XS ON 모드, RTX3090Ti, 컨텍스트 한도262144. 격리된 total(price, quantity) 구현 후 할인·배송비 조건을 두 번 수정.
- None/Low/Medium/High 각각 같은 과제로 비교. temperature=0, 최대 생성1536토큰, 약252K 입력. 최대 생성은 시험 조건이며 사용자 출력32000·추론 예산8192는 변경하지 않았다.
- 실제 Strata 직접 API 호출이다. OpenCode/Rider 화면·전체 에이전트 루프·복잡한 제품 품질·다중사용자 큐 시험은 아니다.
- 서로 다른 추론 단계 및 생성 결과 때문에 과제별 생성 토큰은 달랐다. 적은 표본에서 Low/Medium/High의 일반적인 품질·속도 순위를 주장하지 않는다.

## 기존 start 설정: 단계별 구현과 두 차례 수정

| 단계 | 첫 구현 | 수정1 | 수정2 | 함수 검사 |
|---|---:|---:|---:|---:|
| none | 85.656s | 1.705s | 2.182s | 18/18 |
| low | 85.772s | 3.892s | 8.030s | 18/18 |
| medium | 85.469s | 3.625s | 3.758s | 18/18 |
| high | 85.768s | 6.510s | 4.428s | 18/18 |

각 단계는 동일 초기 대화에서 시작했다. 이전 단계의 긴 대화를 처음으로 되감는 방식이며 네 단계의 첫 요청 모두 cached_tokens=0이었다. 추론만의 비교에는 cold 프리필과 이후 수정 시간을 분리해야 한다.

## 후보 end 설정: 과거 처음으로 되감기

| 단계 | 첫 구현 | 수정1 | 수정2 | 첫 호출 캐시 |
|---|---:|---:|---:|---:|
| none | 85.656s | 1.911s | 2.215s | 0 |
| low | 77.188s | 3.810s | 4.593s | 32000 |
| medium | 77.470s | 4.819s | 4.411s | 32000 |
| high | 77.678s | 8.663s | 3.992s | 32000 |

이 경우 end도 첫 요청으로 되돌아가면32K만 재사용했다. 전체 입력의 되감기 비용이 해결됐다고 주장하지 않는다. 자동 크기 조절 과정에서 start/end 합성 로그가 한두 행 차이 나므로 첫 구현 시간의 작은 차이를 순수 옵션 효과로 단정하지 않는다.

## 같은 65K 대화에서 Low→Medium→High 전환

| 수정 단계 | start 전체시간 | end 전체시간 | start 첫 프리필 | end 첫 프리필 |
|---|---:|---:|---:|---:|
| medium | 28.267s | 3.575s | 21.446s | 0.478s |
| high | 25.852s | 3.335s | 21.482s | 0.395s |

양쪽18개 검사가 모두 통과했다. stage1은 end 쪽에 이전32K 캐시가 남아 있었으므로 초기 작업 시간의 비교에서 제외했다. 전환 시 start의 캐시는0, end는65801/66119였다. 합성 입력 길이는 약65K로 맞췄으며 생성 결과·추론 토큰은 동일하지 않다.
중간 안내의0.67초는 Medium 단계의 다른 호출 값이었다. 위 표는 첫 수정 호출의 원본 값0.478초로 정정했다.

## 최종 적용 후 약252K 대화의 전환

| 단계 | 추론 | 전체시간 | 첫 프리필 | 첫 호출 캐시 | 검사 |
|---|---|---:|---:|---:|---:|
| 1 | low | 87.110s | 84.013s | 0 | 5/5 |
| 2 | medium | 5.769s | 0.617s | 252270 | 6/6 |
| 3 | high | 3.500s | 0.509s | 252757 | 7/7 |

## 적용과 검증

- ON/OFF 프로필 템플릿과 실제 Strata 폴더에 effort_position=end만 추가. 기존 runtime args와 source args의 기존 차이는 보존했다.
- 현재 ON 서버는 관리 재시작으로 적용하고 ready 확인 후 최종252K 검사를 통과했다. OFF는 템플릿 렌더 CPU 검사만 수행했으며 OFF GPU 실행은 하지 않았다.
- 설치 엔진의 --tail-role-token 지원 표식과 서버의 effort_position end 활성화 로그를 확인했다. 구형 엔진은 기존 서버 구현의 fallback 대상이며 동일 개선을 보장하지 않는다.
- 프로필 CPU13개는 변경 전과 변경 후 모두 통과. 격리 코드 검증 CPU2개 통과. 실패한 모델 요청이나 함수 검사는 없었다.
- 기본 추론 수준·모델·출력 한도·추론 예산·기존 GPU 옵션은 바꾸지 않았다. 푸시하지 않았다.
- 추론 비교 도구에 단계별 effort/target/max-output, 같은 대화 stage-efforts, 직렬 matrix 실행 도구를 추가했다.

## 원본 자료

- C:\Users\luiny\Strata-data\diagnostics\reasoning-levels-20261023-a
- C:\Users\luiny\Strata-data\diagnostics\reasoning-levels-20261023-end-a
- C:\Users\luiny\Strata-data\diagnostics\reasoning-switch-20261023-start-a
- C:\Users\luiny\Strata-data\diagnostics\reasoning-switch-20261023-end-a
- C:\Users\luiny\Strata-data\diagnostics\reasoning-switch-20261023-end-252k-a

최종 활성 엔진 PID29212의 실제 명령줄에서 --tail-role-token 활성화를 확인했다. Codex의 AppData 경로 조회는 MSIX LocalCache의 이전 프로필로 resolve되어 effort_position이 없는 사본을 반환했으므로, 해당 사본을 현재 서버 설정의 근거로 사용하지 않았다. 현재 실행 상태는 관리 ready 영수증·실제 엔진 명령줄·최종252K 시험으로 구분해 확인했다.
