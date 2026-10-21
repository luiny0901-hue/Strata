# 자율 코딩 실행 복구 검증 — 2026-10-21

대상은 OpenCode 2.0.22 + Strata Chat Completions 설정입니다. 현재 PC에 runtime plugin과 한국어 복구 지침을 적용했고, Windows/macOS 원격 클라이언트 setup revision 4도 같은 plugin 소스를 설치하도록 연결했습니다. 기존 서버 모델·262144 컨텍스트·32000 출력 한도는 유지합니다. 설정을 다시 읽으려면 OpenCode/Rider ACP 프로세스를 재시작해야 합니다.

## 확인한 동작

| 상황 | 확인한 결과 | 로컬 diagnostics 폴더 |
|---|---|---|
| 완료 후 늦은 자동 알림 | 모델 HTTP 전송 전에 차단, 새 사용자 요청 정상 | autonomy-late-final |
| 셸·자식 작업의 조기 완료/취소 | 부모가 자식 결과를 기다림, 취소 후 남은 파일쓰기 미실행 | acp-turn-child-1, acp-turn-cancel-1, acp-turn-child-cancel-1 |
| ACP 연결 종료 | 소유 shell PID 종료와 남은 명령 미실행 | acp-turn-disconnect-1 |
| length 출력 잘림 | 미완성 호출 미실행, 작은 파일 저장 후 최종 응답 | autonomy-length-final |
| 일반 종료의 잘린 JSON | 불완전한 파일 저장 차단 후 올바른 호출로 복구 | autonomy-invalid-json-2 |
| 도구 인자 오류 | 오류 결과를 받은 같은 요청에서 올바른 파일 저장 | autonomy-tool-error-1 |
| 명령 시간 초과 | 남은 파일쓰기 미실행, 후속 정상 파일 저장 | autonomy-timeout-1 |
| 일시적 HTTP 503 | 같은 요청 안에서 재시도 후 작업 완료 | autonomy-network-once-1 |
| 지속 HTTP 503 | 총 4회 시도 후 오류, 복구 후 새 사용자 요청 정상 | autonomy-network-down-1 |
| 인증 HTTP 401 | 재시도 없이 오류, 인증 복구 후 새 요청 정상 | autonomy-authentication-1 |
| 자동 압축 | 8192/32768/262144 토큰 사용량 모의 → 압축 완료 → 기존 파일 수정 저장 | autonomy-compact-8192-edit, autonomy-compact-32768-1, autonomy-compact-262144-1 |
| ACP 프로세스 재시작/세션 재로드 | 완료 작업 재실행 없음, 새 요청 정상 | autonomy-reconnect-1 |

설치된 OpenCode 실행 파일을 실제 ACP로 실행한 결과이며 모델 응답과 usage는 로컬 모의 HTTP 서버가 제공합니다. 파일 쓰기·수정, 프로세스·취소, 압축·세션 재로드는 실제 OpenCode를 통과합니다. 모델의 문제 해결 지능·코드 품질이나 실제 262K GPU 부하를 검증한 결과는 아닙니다.

## 재설치·외부 PC

- 로컬: `python tools/configure_acp_foreground_guard.py`, `python tools/configure_opencode_output_recovery.py`, `python tools/configure_opencode_session_recovery.py`.
- 외부 PC: 기존 `tools/remote_agent_client` setup을 사용합니다. `strata-acp-foreground-guard`와 `strata-output-recovery` 파일도 설치 및 doctor 해시 검사 대상입니다. CUA 사용 여부와 무관하게 복구 plugin을 설치합니다. 다른 ACP 항목과 기존 env는 보존합니다.
- CUA 입력은 background와 AI overlay만 사용합니다. UAC·인증·background 미지원 GUI는 현재 제한에서 완전자동으로 처리하지 못하므로 저장된 작업과 정확한 차단 사유를 보고합니다.
- 단계 제한 전에 인계 상태를 남기고, 완료한 작업은 중복 구현하지 않습니다. 명시적 새 사용자 요청 없이 완료한 작업을 자동으로 다시 열지 않습니다.

## 실패 시도 보존

- `autonomy-invalid-json-1`: native JSON 보정으로 불완전 내용이 파일에 저장되는 문제를 실제 확인했고 stream 검증을 추가했습니다.
- `autonomy-compact-8192-1`: 모의 모델의 요약 형식이 잘못되어 실패했습니다.
- `autonomy-compact-8192-2`: 요약을 형식에 맞게 바꿨지만, 테스트가 compaction에도 도구 목록이 실린다는 사실을 반영하지 못해 일반 최종 답변을 반환했습니다. 요청 body에서 요약/nudge를 구분하도록 고친 다음 `-3` 및 `-edit` 실행에 통과했습니다.
- 원시 사용자 DB나 비밀키는 저장소에 복사하지 않습니다. 각 재현 명령은 별도의 새 diagnostics 폴더와 격리 DB를 사용합니다.

실제 Rider 화면 및 Strata GPU로 장기간 운영하는 결과, Apple Silicon GUI, 타사 plugin의 독자 루프·비동기 slash command는 미검증입니다. 모든 가능한 장애나 OS 보안 경계를 자동 해결한다고 주장하지 않습니다.
