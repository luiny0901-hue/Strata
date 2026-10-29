# Linux NVFP4 서버 준비와 외부 클라이언트

상태: Linux 서버 준비·실행 절차를 설명합니다. Linux 성능, 포크 바이너리 호환성,
실제 원격 연결은 미검증입니다.

## 통합 설치

`bash install-strata-agent.sh --role server`로 Python 준비·서버 의존성·GPU 선택·복구 자료 확인·기존 ON/OFF 프로필 준비를 진행할 수 있습니다. Linux 의존성 단계는 아래 기존 부트스트랩을 재사용합니다. 모델·Pack·동일 포크 Linux 바이너리는 백업을 복원하며, 누락 파일이나 드라이버·재부팅 단계는 대기로 남습니다. [통합 설치 안내](INTEGRATED_INSTALL_KO.md)를 참고하세요.

## 서버 파일 준비

`SETUP-LINUX-SERVER.sh`는 Python/venv/pip와 저장소의 Python 의존성을 자동 준비합니다.
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

## Claude Desktop Code 클라이언트

Claude Desktop Code는 Strata 서버와 별도의 클라이언트 PC에서 실행할 수 있습니다. 권장 외부 연결은 접속 PC에서 OpenCodex를 실행하고 SSH 터널로 Linux 서버의 127.0.0.1:8080을 접속 PC의 127.0.0.1:18080에 연결하는 방식입니다. OpenCodex의 Strata 공급자에는 http://127.0.0.1:18080/v1과 서버 API 키를 설정합니다. 터널·클라이언트 준비는 [Claude 연결 안내](CLAUDE_OPENCODEX_KO.md#새-pc재설치외부-pc)를 따릅니다. 위 LAN 직접 바인딩 예시는 별도의 서버 운영 선택이며, 현재 로컬 전용 유지보수 진단과 혼용하지 않습니다. CUA Driver·REA는 화면과 파일을 실제로 다루는 클라이언트 PC에서 준비합니다. Linux 서버에 GUI용 CUA를 설치하지 않습니다.

이 문서는 Linux 서버의 프로필 준비와 실행만 설명하며 외부 PC·Apple Silicon Mac에서의 Claude Desktop Code 연결을 검증했다는 뜻은 아닙니다.
