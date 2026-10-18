# OpenCode 장기 작업 세션 복구 설정

Windows와 macOS의 OpenCode에서 장기 코딩 세션이 작업 상태를 다시 확인하고, 명령 실행을 기다리며 멈추거나 도구 호출을 반복하는 문제를 줄이는 opt-in 설정입니다. Strata 서버, 모델, GPU, Rider 프로젝트 파일은 변경하지 않습니다.

저장소 루트에서 실행합니다.

~~~powershell
& "$env:USERPROFILE\Strata\.venv\Scripts\python.exe" tools\configure_opencode_session_recovery.py
~~~

Windows에서 해당 Strata Python 환경을 사용하지 않는 경우 Python 3.10 이상이 설치되어 있으면 py -3 명령으로 실행할 수 있습니다. macOS에서는 다음을 실행합니다.

~~~sh
python3 tools/configure_opencode_session_recovery.py
~~~

다른 OpenCode 설정 파일을 사용하는 경우에는 --config를 지정할 수 있습니다. 격리된 테스트 설정에는 --instructions-dir와 --source-instructions를 함께 지정할 수 있습니다.

## 적용 값

- 자동 context compaction을 켭니다.
- 최근 대화 보존량을 12,000 토큰으로 설정합니다.
- 모델의 context limit 아래 65,536 토큰을 compaction 여유로 둡니다. 262K 모델에서는 세션이 한도에 닿기 전에 요약을 시작합니다.
- Build agent의 최대 단계를 60으로 제한합니다. 제한에 도달하면 OpenCode가 도구를 제거하고 텍스트로 진행 상태를 요약합니다.
- 아래의 한국어 복구 지침 파일을 OpenCode 전역 instructions 목록에 추가합니다.

기존 provider, model, API key, 권한 및 기타 설정은 보존합니다. 실제 config는 저장소에 포함하지 않습니다. 변경 전 설정 백업은 config 파일 옆에 생성됩니다. 같은 도구를 다시 실행하면 이미 적용된 값은 중복 추가하지 않습니다.

## 세션 복구 규칙

재부팅, Rider/OpenCode 재시작, 작업 중단 뒤에는 현재 Git 상태와 diff, 작업 인계 문서, 관련 프로세스를 먼저 확인합니다. 이미 반영된 코드를 다시 구현하지 않고 누락된 확인과 검증만 이어갑니다.

UAC 승인을 기다리는 Start-Process -Verb RunAs -Wait와 장기 실행 프로세스를 기다리는 셸 명령을 실행하지 않습니다. 관리자 권한이 필요한 경우 비대화형 스크립트를 준비해 사용자가 관리자 PowerShell에서 실행한 결과를 받은 뒤 계속합니다. 오래 걸리는 셸 명령에는 제한 시간을 두고, 서버·워처는 백그라운드로 실행합니다. 작업이 멈춘 것 같으면 새 명령을 시작하기 전에 기존 프로세스와 셸 상태를 확인합니다.

Strata 로그의 done (stop, cancel=False)는 모델 생성 또는 도구 호출 생성이 끝났다는 표시입니다. OpenCode가 도구를 실행하고 결과를 돌려줄 수 있으므로, 이 로그만으로 전체 작업이 끝났다고 판단하거나 같은 요청을 다시 보내지 않습니다. 도구 단계 제한에 도달하면 완료·미완료·검증·다음 행동을 요약합니다.

## 적용 확인과 복구

도구는 JSON을 다시 읽어 파싱하고, config에 변경 전 백업을 남깁니다. OpenCode가 실행 중인 세션은 이미 읽은 설정을 계속 사용할 수 있습니다. 진행 중인 작업을 끊지 말고 안전한 지점에서 OpenCode를 재시작한 다음 새 세션 또는 재개 세션에서 확인합니다.

잘못된 config 형식이면 설치기는 수정을 거부하고 파일을 보존합니다. 복구가 필요하면 출력된 백업 파일을 이용해 이전 config를 복원할 수 있습니다. 자동으로 Strata 서버를 재시작하거나 GPU 작업을 실행하지 않습니다.
