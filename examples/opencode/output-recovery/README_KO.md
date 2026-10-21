# 긴 코드 생성과 출력 잘림 복구

설치: `python tools/configure_opencode_output_recovery.py` 실행 후 OpenCode/ACP 연결을 다시 시작합니다. 기존 설정을 보존하고 변경 전 백업을 만듭니다. 기본 적용 대상은 `strata` 공급자의 Chat Completions SSE 응답이며, 컨텍스트 262144와 출력 한도 32000은 변경하지 않습니다.

완료시간의 낭비를 줄이기 위해 기존 파일은 부분 수정하고, 새 파일은 역할별로 분리하며 write의 content 스키마와 지침에 16000자 예산을 제공합니다. 실제 모델이 생성하기 전에 따르는 예산이며, 완성된 파일을 사후에 강제로 자르지 않습니다. 매 저장마다 전체 빌드를 반복하지 않고 요청된 검증 시점에 확인하도록 안내합니다.

HTTP 응답에서 일반 텍스트와 reasoning은 계속 스트리밍하고 도구 인자만 종료 사유 확인까지 보관합니다. `length`이면 미확정 도구 호출을 폐기하고 내부 `strata_output_recovery` 호출로 바꿔 같은 OpenCode 루프에서 작은 호출로 이어가게 합니다. 파일 변경은 기존 write/edit 도구가 담당하며, 이 플러그인은 잘린 코드를 저장하거나 임의로 완성하지 않습니다. 복구 도구 결과에 잘림과 미실행 사실을 명시합니다. 연속 잘림은 최대 2회 복구하고 세 번째는 원래 length 종료를 유지합니다. 정상 생성이 끝나면 연속 실패 횟수를 초기화합니다. 사용자 취소는 새 작업으로 재개하지 않습니다.

SSE가 finish_reason 없이 끊기면 미확정 인자를 실행하지 않고 오류를 반환합니다. 보관 크기는 8MiB로 제한합니다. 도구 인자는 완료 확인 후 전달되므로 스트림 중의 도구 작성 표시가 늦게 나타날 수 있습니다. 완료된 일반 호출은 다시 실행하지 않습니다.

2026-10-21 검증:

- Node 5개: UTF8/SSE 분할, 정상 호출 보존, length 복구, 세 번째 실패 제한, 연결 중단 시 미실행 통과.
- 설치된 OpenCode 2.0.22 ACP + 로컬 모의 모델: 잘린 write 미실행 → 복구 결과 전달 → 작은 write의 실제 파일 저장 → 최종 응답/end_turn 통과.
- 기존 session recovery/CUA 설정 테스트 22개 통과.
- 실제 Strata GPU 모델로 장문 프로젝트의 완료시간 절감률은 측정하지 않았습니다. 16000자 예산 준수와 코드 품질은 모델의 판단도 필요합니다. Responses/WebSocket/비SSE 응답에는 이 스트림 복구를 적용하지 않습니다.
- 첫 ACP 복구 테스트는 후속 shell 실행을 확인했습니다. 파일 저장으로 검증을 강화한 첫 시도에서는 테스트가 write의 path 대신 filePath를 사용해 파일 미생성으로 실패했습니다. 실제 카탈로그의 path로 수정한 다음 시도에서 저장까지 확인했습니다. 실패 증거는 로컬 diagnostics/output-recovery-small-write, 통과 증거는 diagnostics/output-recovery-small-write-corrected에 보존했습니다.

재현: `node --test tools/test_output_recovery.mjs`, `python tools/test_acp_foreground_runtime.py --output-recovery --binary <opencode.exe> --output <새 진단 폴더>`.

일반 종료에서도 JSON 인자가 불완전하면 OpenCode가 보정한 부분 내용을 저장할 수 있어, tool arguments를 종료 시점에 JSON 객체로 검사하도록 추가했습니다. 잘못된 JSON은 미확정 호출 전체를 폐기하고 `INVALID_TOOL_JSON`으로 복구하며, 복구 예산 초과는 성공 대신 오류로 종료합니다. provider의 content_filter 응답은 그대로 거절로 유지하고 재시도하지 않습니다. 모의 모델로 이 문제를 실제 재현한 실패 폴더는 `diagnostics/autonomy-invalid-json-1`, 수정 후 파일 미생성과 후속 정상 저장 확인은 `diagnostics/autonomy-invalid-json-2`입니다. 현재 스트림 단위 테스트는 8개입니다.
