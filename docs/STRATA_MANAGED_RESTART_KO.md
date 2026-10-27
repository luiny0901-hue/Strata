# Claude를 통한 Strata 관리 재시작

Claude Desktop Code의 `strata-maintenance` MCP가 서버 관리 기능을 사용합니다. 일반 API 연결만으로는 프로세스 제어 권한이 생기지 않습니다. 제어 API는 Strata 관리 실행기가 소유하며 `127.0.0.1:8768`에만 바인딩합니다.

## Windows 서버에서 관리 실행기 켜기

아래 설정은 다음 일반 ON/OFF 실행부터 supervisor를 사용합니다. 지금 실행 중인 서버는 중단하거나 바꾸지 않습니다.

```powershell
py tools\configure_strata_managed_launchers.py --managed-launchers
```

일반 실행을 되돌리려면 `%USERPROFILE%\.config\strata\server-control\managed-launchers.enabled` 파일을 지우고 서버를 다음에 시작합니다. BAT에 `--managed`를 붙여 한 번만 관리 실행할 수도 있습니다. 관리 창을 닫으면 해당 실행기가 소유한 Strata 서버도 종료됩니다.

Linux에서는 준비된 서버에 `--managed`를 지정해 실행합니다.

```sh
./run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh --managed
```

## 재시작 동작과 체크포인트

허가된 서버 코드·설정 수정에 재시작이 필요할 때만 사용합니다. 체크포인트에는 완료한 일, 남은 일, 파일 경로, 확인할 내용을 기록합니다. 서버 변경은 Strata 관리 실행기만 수행합니다.

1. 실행 중인 Strata 요청이 끝났는지 확인합니다. 상태가 없거나 바쁘면 재시작하지 않습니다.
2. 해당 관리 실행기가 소유한 프로세스 트리만 종료합니다. 무관한 포트 소유 프로세스를 찾아 종료하지 않습니다.
3. 같은 ON/OFF 실행기를 시작하고 인증된 모델 준비 상태를 확인합니다.
4. 같은 작업 요청에서 저장된 체크포인트로 돌아가 남은 작업을 마칩니다. 자동 재전송은 하지 않습니다.

전달 결과가 불확실하면 같은 `operation_id`와 체크포인트로 상태를 확인합니다. 새 ID로 재시작을 반복하지 않습니다. 취소·프로세스 종료·재부팅 뒤 작업을 자동 재개한다고 가정하지 않습니다.

Claude 설정에 `strata-maintenance`가 등록되어 있으면 MCP 정본은 `~/.claude/strata-mcp.json`입니다. 상태 확인은 읽기 전용이며, 재시작과 취소는 별도 도구입니다. 설정기는 상태 확인 권한만 관리하며 재시작 동작을 자동 승인하지 않습니다.

## 외부 클라이언트

제어 포트를 인터넷이나 방화벽에 직접 공개하지 않습니다. 이미 허가된 SSH 계정으로 로컬 터널을 열어 사용합니다.

```sh
ssh -N -L 8768:127.0.0.1:8768 SERVER_USER@SERVER_ADDRESS
```

서버 관리 키는 승인된 Claude 클라이언트의 비공개 설정에만 보관합니다. 키 내용은 모델 프롬프트에 넣지 않습니다.

## 검증 범위

supervisor의 소유 프로세스·로그·재시작 상태는 격리 CPU fixture 테스트로 확인할 수 있습니다. 이 검사는 실 GPU 모델 재시작, 실제 Claude Desktop의 재시작 승인 흐름, 외부 PC·Linux 운영을 증명하지 않습니다. 새 환경의 실제 실행은 별도로 확인해야 합니다.
