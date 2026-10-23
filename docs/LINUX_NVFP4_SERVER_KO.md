# Linux NVFP4 서버 준비와 외부 클라이언트

상태: 실행 경로를 추가하고 이후 요청에 따라 [오프라인 문법·모의 검사](AGENT_SETUP_VALIDATION_KO.md)를 수행했습니다.
Linux 성능, 포크 바이너리 호환성, 실제 원격 연결은 미검증입니다.

## 서버 파일 준비

`SETUP-LINUX-SERVER.sh`는 이제 Python/venv/pip와 저장소의 Python 의존성을 자동 준비합니다.
범위와 수동으로 준비할 아티팩트는 [자동 준비 안내](AUTOMATIC_SETUP_KO.md)를 참고하세요.
아래 `prepare` 설명의 프로필 생성 전에 의존성 설치가 진행됩니다.

Windows는 기존 무검열 ON/OFF BAT을 사용합니다. Linux는 같은 이름의 `.sh`를 사용합니다.
Linux 실행기는 기존 ON/OFF JSON 템플릿의 추론 인자를 재사용하며 Linux 경로와 실행 파일명,
GPU 번호를 적용합니다. 컨텍스트 262144, CPU 비전, 이미지 토큰 상한 1024를 사용합니다.
기본 GPU는 0이며 Windows BAT의 GPU 1을 그대로 가정하지 않습니다.

Python 3.10 이상과 NVIDIA 드라이버가 필요합니다. Linux 배포판과 GPU에 맞게 **동일 포크 버전**의
서버 Python 의존성과 Linux 네이티브 엔진을 먼저 준비해야 합니다. 일반 Strata 엔진이나
Windows `.exe`로 대체하지 마세요. 이 실행기는 엔진을 내려받거나 빌드하지 않습니다.
포크의 Linux 바이너리가 없으면 해당 포크의 빌드 절차로 준비해야 합니다.

기본 디렉터리:

- 저장소 `.venv/bin/python`: 포크 서버 의존성을 설치한 Python 환경
- 저장소 `forks/sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2/strata-nvfp4/`:
  해당 버전의 `serve/`, `release-manifest.json`, `engine/strata`, `engine/strata-vision`,
  `data/uncensor/qwen-nvfp4-gptq-uncensored.gguf`
- 저장소 `data/expert-profile.bin`
- `~/Strata-data/models/unsloth-UD-IQ4_XS/`: GGUF 3개
- `~/Strata-data/models/mmproj-Qwen3.8-Flash-Next-BF16.gguf`
- `~/Strata-data/packs/unsloth-ud-iq4_xs/`: 기존 네이티브 팩과 토크나이저
- `~/Strata-data/mtp/rt/`: dense.bin, experts.bin, draft_vocab.bin

모델·팩을 재설치 전 별도 디스크에 보관하면 재사용할 수 있습니다. 기존 파일은 삭제하지 않습니다.
Windows의 경로가 들어간 JSON을 그대로 복사하지 말고 Linux에서 프로필을 생성하세요.

## 준비와 실행

저장소 디렉터리에서 다음을 실행합니다. 준비 명령은 Python 의존성을 설치하고 프로필과 개인 API 키 파일을 생성합니다.
기존 키는 보존하며 출력하지 않습니다.

```sh
sh SETUP-LINUX-SERVER.sh --mode on
sh SETUP-LINUX-SERVER.sh --mode off

# 같은 Linux PC에서만 사용
sh run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh

# 외부 Windows/Mac에서 사용: 서버의 LAN 또는 Tailscale IP에만 바인딩
sh run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh --host 192.168.1.20 --gpu 0
sh run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.sh --host 100.100.100.20 --gpu 0
```

위 IP는 예시이므로 실제 서버 주소로 바꾸세요. ON/OFF는 같은 포트를 사용하므로 하나씩 실행합니다.
실행기는 별도 백그라운드 프로세스를 만들지 않으며 서버 종료 코드를 전달합니다. Ctrl+C로 종료합니다.
포트가 이미 사용 중이면 기존 프로세스를 종료하지 않고 서버 자체의 바인딩 오류로 종료됩니다.

외부 디스크와 포크 경로가 다르면 준비와 실행 양쪽에서 같은 옵션을 지정합니다.

```sh
sh SETUP-LINUX-SERVER.sh --data-root /mnt/models/Strata-data --fork-root /opt/strata-nvfp4 --python /opt/strata-venv/bin/python
sh run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh --data-root /mnt/models/Strata-data --fork-root /opt/strata-nvfp4 --python /opt/strata-venv/bin/python --host 192.168.1.20
```

API 키는 `${XDG_CONFIG_HOME:-$HOME/.config}/strata/STRATA_API_KEY`에 저장됩니다(0600).
키가 잘못되면 덮어쓰지 않고 중단합니다. Linux 방화벽은 자동 변경하지 않습니다.
배포판 방화벽에서 TCP 8080을 실제 LAN 서브넷 또는 필요한 Tailscale 경로에만 허용하세요.
인터넷 공유기 포트포워딩은 필요하지 않으며 외부 네트워크에서는 Tailscale 주소를 권장합니다.
`0.0.0.0`을 선택하면 모든 인터페이스에 바인딩하므로 방화벽 범위를 먼저 설정해야 합니다.

## 외부 Windows / Apple Silicon Mac

서버가 Windows인지 Linux인지와 무관하게 클라이언트 설정은 같습니다.
서버 주소 `http://서버주소:8080`과 위 API 키를 클라이언트 설치 과정에 입력합니다.

| 작업 | Windows | Apple Silicon Mac |
|---|---|---|
| 최초 설정 | `SETUP-OPENCODE.bat setup` | `sh setup-opencode.sh setup` |
| 사용 | `SETUP-OPENCODE.bat run` | `sh setup-opencode.sh run` |
| 사용자가 원할 때 진단 | `SETUP-OPENCODE.bat doctor` | `sh setup-opencode.sh doctor` |

OpenCode·CUA·REA는 클라이언트에 설정됩니다. CUA가 조작하는 화면도 클라이언트 화면입니다.
서버에서 Linux GUI CUA를 설치할 필요는 없습니다. Mac의 화면 기록·손쉬운 사용 권한은 직접 허용합니다.
Python·Node·OpenCode 등 클라이언트 선행 조건과 설치 범위는
[클라이언트 안내](../tools/remote_agent_client/README_KO.md)를 따릅니다.
이 문서는 실제 Linux/Mac 동작을 검증했다는 뜻이 아닙니다.
