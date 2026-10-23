# 코딩 중 Strata 서버 재시작

## 시작 방법

이 기능은 선택 사항이다. 실행 중인 일반 서버를 강제로 가져오거나 종료하지 않는다. 관리 모드를 선택하지 않은 기존 실행기는 종전 방식이고, 아래 관리 실행기는 별도 프로세스가 서버를 소유한다.

Windows에서는 현재 서버를 정상 종료한 다음 다음 중 하나를 실행한다.

- `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on-managed.bat`
- `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off-managed.bat`

기존 BAT에 `--managed`를 붙여도 같다. 모델·GPU·비전·인증·방화벽 검사는 기존 BAT를 그대로 사용한다. 관리 프로세스는 같은 BAT를 비대화형으로 재실행한다. 서버 로그는 `~/Strata-data/supervisor/server.log`, 재시작 체크포인트와 작업별 결과는 같은 폴더에 남는다. 화면에 `Managed Strata ready`가 나와야 준비 완료다. 관리 창을 닫으면 소유 서버도 종료된다.

Windows 서버 PC에서 아래 명령으로 선택 설정을 저장하면, 다음부터 기존 ON/OFF BAT를 인자 없이 실행해도 관리 모드로 시작한다. 이미 실행 중인 서버는 전환하거나 종료하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools\configure_strata_server_lifecycle.py --managed-launchers
```

선택 파일은 `~/.config/strata/server-control/managed-launchers.enabled`다. 이 파일을 제거하면 다음 일반 BAT 실행부터 기존 방식으로 돌아간다. `--managed` 명시 실행은 계속 사용할 수 있다. 이 선택은 해당 Windows 서버 PC에만 적용되며 Linux SH 및 외부 클라이언트에 자동 전파되지 않는다. 관리 자식 프로세스는 선택 파일이 있어도 다시 관리자를 만들지 않는다.

서버 출력은 줄 길이와 무관하게 별도 읽기 경로로 계속 비운다. 로그는 파일당 8MiB, 현재 파일과 백업 3개로 최대 32MiB를 보존한다. 이전 버전의 큰 로그도 각 파일의 최신 8MiB만 유지하므로 오래된 출력은 삭제된다. 작업 체크포인트·작업별 결과·진단 폴더에는 이 순환 삭제를 적용하지 않는다. 로그 기록 실패는 오류로 표시하며 출력 파이프가 가득 차 서버가 멈추지 않도록 계속 읽는다. 상태 조회에는 긴 체크포인트를 재전송하지 않고 작업 ID·상태·취소·오류만 반환한다.

OpenCode에 도구가 없으면 저장소 루트에서 다음을 실행하고 OpenCode/ACP를 재시작한다.

```powershell
.\.venv\Scripts\python.exe tools\configure_strata_server_lifecycle.py
```

기존 모델·API 키·CUA·REA 설정은 유지하며 버전이 고정된 `strata_restart_server` 플러그인만 추가한다. 처음 관리 서버를 실행하면 전용 제어 키가 `~/.config/strata/server-control/restart-control.key`에 생성된다. 모델에는 키 내용이 전달되지 않는다.

Linux에서는 기존 준비가 끝난 상태에서 실행한다. 관리 기능이 모델·드라이버·엔진을 설치하지는 않는다.

```sh
./run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh --managed
.venv/bin/python tools/configure_strata_server_lifecycle.py
```

Linux 실행 경로는 준비했으며 실제 Linux 프로세스/GPU 재시작은 미검증이다. 관리 모드는 해당 SH의 기본 프로필을 사용한다. 일반 서버 실행용 `--gpu` 등의 옵션을 관리 명령에 그대로 넘기지 않는다.

## 에이전트 동작

사용자가 허가한 Strata 코드/설정 변경에 재시작이 필요하면 파일을 저장한 뒤 도구에 고유 `operation_id`와 `checkpoint`를 전달한다. 체크포인트에는 완료한 일, 남은 일, 정확한 파일 경로, 남은 검증을 기록한다. 도구의 용도는 서버 재시작이며 작업 범위를 확대하지 않는다.

1. 외부 관리 프로세스가 체크포인트를 디스크에 저장한다.
2. `/slots`의 처리 중 상태를 최대 60초 확인한다. 상태를 알 수 없거나 계속 사용 중이면 종료하지 않고 실패를 반환한다.
3. 소유 프로세스 트리만 종료한다. Windows는 실행 전 Job Object에 편입한 대기 프로세스를 통해 자식 생성을 시작하고, 종료 후 활성 프로세스가 0인지 확인한다.
4. 기존 포트가 해제된 경우에만 같은 실행기를 시작한다. `/health`의 loaded 상태와 인증된 `/v1/models`의 지정 모델을 최대 600초 확인한다.
5. 기다리던 OpenCode 도구가 READY를 반환하고, 같은 요청에서 남은 작업을 이어간다. 새 사용자 메시지나 완료 후 자동 알림을 만들지 않는다.

전달 여부가 불확실하면 같은 ID와 같은 체크포인트를 사용한다. 같은 요청은 다시 서버를 종료하지 않고 저장된 결과를 반환한다. 다른 ID를 만들어 무작정 재시도하지 않는다. 전체 도구 대기는 최대 900초다. 성공은 API 모델 준비 상태이며 재시작 후 실제 기능 검증은 에이전트의 남은 작업이다.

취소가 종료 전에 도착하면 서버를 유지한다. 이미 종료했다면 서버 복원까지만 수행하고 취소 상태로 끝낸다. 에이전트 작업을 자동 재개하지 않는다. 관리 프로세스 자체가 중단된 작업은 다음 시작에 실패로 기록하며 임의 재실행하지 않는다.

## 외부 Windows·Apple Silicon Mac

일반 추론 API 연결만으로 서버 프로세스 제어 권한이 생기지는 않는다. 제어 API는 **서버의 127.0.0.1:8768에만** 바인딩한다. 서버의 기존 SSH 접속이 준비되어 있고 해당 사용자가 서버 재시작 권한을 부여받았다면 클라이언트에서 터널을 연다.

```sh
ssh -N -L 8768:127.0.0.1:8768 SERVER_USER@SERVER_ADDRESS
```

서버 관리 전용 키 파일을 허가된 클라이언트의 비공개 폴더로 안전하게 복사하고 `configure_strata_server_lifecycle.py --control-url http://127.0.0.1:8768 --token-file LOCAL_PRIVATE_KEY_PATH`로 등록한다. 서버 SSH 설치·계정·터널 자동 연결과 실제 외부 PC 검증은 포함하지 않았다. 제어 포트를 방화벽이나 인터넷에 직접 공개하지 않는다.

## 경계와 검증

- 관리 밖의 서버가 포트를 사용하면 시작을 거부한다. 관리자 승격이나 포트 소유 프로세스 강제 종료를 하지 않는다.
- 여러 클라이언트가 계속 새 요청을 보내는 상황의 원자적 요청 차단 기능은 없다. 유휴 확인 직후 새 요청이 들어오면 끊길 수 있으므로 공유 서버는 재시작 동안 신규 작업을 멈춰야 한다. 미완료 쓰기·클릭을 자동 재전송하지 않는다.
- 관리 프로세스·OpenCode·OS 자체 재시작이나 재부팅 후 무인 자동 재개는 이 기능의 범위가 아니다. 관리 코드 변경은 다음 관리 실행부터 적용된다.
- 설치된 OpenCode 2.0.22 + 실제 외부 관리 프로세스 + CPU 모의 모델로, 자식 서버 교체 → 인증된 모델 준비 → 같은 ACP 요청의 후속 생성 → 최종 end_turn을 검증했다. 실제 GPU Strata, Rider, Hermes, Linux, macOS 실행을 검증한 것은 아니다.
- 첫 통합 시도 `managed-restart-20261022-a`는 테스트가 제목 생성 요청까지 작업 요청으로 세어 실패했다. 제목 생성을 분리한 `-b`와 Windows 프로세스 편입 순서 보완 후 `-c`는 통과했다. 각 시도 기록은 `~/Strata-data/diagnostics/`에 따로 보존했다.
- 취소 요청이 재시작 전달보다 먼저 도착해도 취소 기록을 남겨 늦은 재시작이 시작되지 않도록 보완했다. 최종 `managed-restart-20261022-d`도 같은 ACP 요청 내 복귀를 통과했다.
- Python 회귀 58개, 별도 실행한 IQ4_XS 프로필/실행기 검사 13개, Node 테스트 28개가 통과했다. ACP guard의 기존 검사도 통과했다. 첫 Python 묶음 실행에는 독립 실행형 `test_iq4xs_opencode_setup.py`를 모듈 방식으로 불러와 import 실패가 1건 있었다. 파일을 직접 실행해 13개 통과를 확인했으며 실패 이력은 성공으로 덮어쓰지 않는다. SH 두 파일은 Git Bash의 `bash -n` 구문 검사를 통과했다.
- 현재 Windows PC에는 실행기·외부 관리 코드·복구 지침·버전 고정 플러그인을 백업 후 반영했다. 설치 기록은 `managed-restart-install-20261022.json`이다. 기존 실행 중인 Strata와 OpenCode/ACP 프로세스를 중단하거나 새 GPU 서버를 실행하지 않았다. 관리 실행기와 새 OpenCode/ACP 세션을 사용해야 활성화된다.
