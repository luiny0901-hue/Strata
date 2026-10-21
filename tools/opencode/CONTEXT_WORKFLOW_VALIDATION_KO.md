# 컨텍스트와 장기 코드 작업 점검 (2026-10-21)

## 변경

- output-recovery 플러그인에 provider 범위의 compaction 훅을 추가했다. ACP 환경변수가 없는 일반 OpenCode도 압축 요약에 최신 요청, 완료 조건, 관련 경로, 저장된 부분과 남은 부분, 실제 검증, 불확실한 부작용을 보존하도록 지시한다.
- 압축 후 관련 파일 구간과 diff를 대조하고 검색 결과가 잘리면 검색 범위를 좁히도록 전역 복구 지침을 보완했다.
- 기존 262144 컨텍스트와 32000 출력 설정은 유지했다. 지침은 모델 행동에 대한 보장이 아니다.

## 이번 실행 증거

- `node --test tools/test_output_recovery.mjs`: 9/9 통과. ACP 없이 압축 훅 등록, 잘린 도구 인자 폐기, 잘못된 JSON 복구 제한, 연결 끊김과 거부 유지 포함.
- `python -m unittest tools.test_verify_opencode_262k_workflow tools.test_remote_agent_client`: 11/11 통과.
- 설치된 OpenCode 2.0.22의 격리 ACP + 모의 SSE 모델: 65536, 131072, 262144 예산 각각 자동 압축 완료 후 저장된 파일의 후속 수정 통과.
- 262144 시나리오에 32개 모듈의 중첩 파일 2048개를 추가한 실행: 압축과 후속 수정 통과, 관련 없는 파일 전부 SHA256 동일.
- 진단 폴더: `C:\Users\luiny\Strata-data\diagnostics\context-hardening-*-20261021` 및 `context-hardening-manyfiles-20261021`. 각 실행의 events.json, requests.json, stderr.log 보존.
- 전역 output-recovery 플러그인과 복구 지침 설치 완료. 설정 JSON 변경 없음. 재설치 클라이언트는 같은 소스 자산을 패키징한다.

## 증거 한계

## 추가 통신 점검

2026-10-21: 기존 SSE 처리에서 도구 인자 사이의 주석형 keepalive를 미확정 종료로 오인하는 경로를 수정했다. 주석은 그대로 전달하며 실제 [DONE]에만 종료 확인을 요구한다. 텍스트만 생성하다 끊긴 응답도 finish_reason이 없으면 명시적인 오류로 끝나며, 손상된 SSE JSON을 하위 도구 복구기로 넘기지 않는다. 새 자동 재시도 루프는 추가하지 않았다.

`node --test tools/test_output_recovery.mjs`: 14개 통과. 실제 설치된 OpenCode + 모의 모델의 출력 제한 복구, malformed JSON 복구, 262144 예산 자동 압축 후 수정 각각 통과. 진단 경로는 `autonomy-stream-final-0-20261021`, `autonomy-stream-final-1-20261021`, `autonomy-stream-final-2-20261021`이다. 실제 GPU 모델과 Rider 화면 검증은 포함하지 않는다.

## 실측 범위

토큰 사용량은 모의 응답이 보고한 값이며 실제 262K 프롬프트를 채운 GPU 시험이 아니다. 도구 순서도 모의 모델이 지정한다. 2048개 파일 시험은 주변 파일 보존을 검증하며 실제 모델의 탐색·설계·코드 정확도를 검증하지 않는다. Rider/Hermes, 외부 PC, 실제 Strata의 긴 코드 생성과 반복 압축 성능은 이번 실행에서 검증하지 않았다. 모든 변수에서 무조건 자율 완료한다고 보장하지 않는다. 권한·인증·지속 오류·단계 한계에서는 현재 상태와 미완료 작업을 보고해야 한다.
