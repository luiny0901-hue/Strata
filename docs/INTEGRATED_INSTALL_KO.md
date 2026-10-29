# Strata 통합 설치

## 처음 실행

최신 저장소를 새 폴더에 풀고 다음 파일을 실행합니다. 기존 PC의 `.venv`는 복사하지 않습니다.

- **Windows:** `INSTALL-STRATA-AGENT.bat`를 실행하고 `접속 PC` 또는 `서버 복구·준비`를 선택합니다.
- **Apple Silicon Mac:** 터미널에서 저장소 폴더의 `bash install-strata-agent.sh`를 실행합니다. 실행 권한이 있는 `INSTALL-STRATA-AGENT.command`도 같은 설치기를 엽니다. 처음 한 번 `chmod +x INSTALL-STRATA-AGENT.command`로 실행 권한을 줄 수 있습니다.
- **Linux NVIDIA 서버:** `bash install-strata-agent.sh --role server`를 실행합니다.

한국어 안내에 따라 진행합니다. 재부팅·설치 오류·네트워크 끊김으로 멈췄으면 같은 파일을 다시 실행합니다. 설치 기록만 믿고 건너뛰지 않고 실제 설치 상태를 다시 확인합니다. 결과가 불확실한 설치는 이전 설치 창/프로세스 종료를 확인하기 전 재실행하지 않습니다.

실행 전에 계획만 보려면 Windows는 `INSTALL-STRATA-AGENT.bat --role client --plan`, Mac은 `bash install-strata-agent.sh --role client --plan`, Linux는 `bash install-strata-agent.sh --role server --plan`을 사용합니다. 계획 모드는 프로그램 설치·연결 설정·서비스 변경을 하지 않습니다. Python이 없는 경우에도 부트스트랩은 설치 계획만 표시하고 종료합니다.

## 접속 PC에 포함된 설치

| 항목 | 처리 |
| --- | --- |
| Python | 기존 Python 3.10 이상 재사용, 없으면 Windows winget의 Python 3.12 또는 Mac Homebrew의 python@3.12 설치 |
| Node.js/npm | 기존 지원 버전 재사용, 없으면 Windows Node.js LTS / Mac node 설치 |
| Claude Desktop | 기존 앱 재사용, 없으면 Windows winget / Mac Homebrew cask 설치 |
| CUA Driver | 기존 실행 파일 재사용, 없으면 공식 설치기로 검증된 연결 버전 0.36.0 설치 |
| OpenCodex | 기존 서비스 소유자/설치 재사용, 없으면 npm 패키지 2.92.0 설치 |
| REA | 기존 고정 버전 캐시 재사용, 없으면 6.7.0 패키지 준비 |
| 연결 설정 | 기존 OpenCodex 관리 API와 Claude 설정기를 사용해 공급자·262K·추론 정보·지연 MCP·Desktop 게이트웨이 연결 |

Windows 앱 설치 관리자(winget)가 없으면 설치 주소를 안내합니다. Mac에 Homebrew가 없고 설치에 필요하면 Homebrew 공식 설치기를 실행합니다. OS 암호·UAC·패키지 설치 동의·Mac 접근성/화면 기록은 사람이 확인해야 하며 설치기가 대신 누르지 않습니다. 사용자 지정 `STRATA_CLAUDE_PYTHON`·`STRATA_CUA_DRIVER_EXE`가 잘못되면 임의 대체하지 않습니다.

원격 서버 선택 시 서버 주소와 API 키만 입력하면 됩니다. API 키 입력은 화면에 표시하지 않으며 설치 기록이나 프로세스 인자에 저장하지 않습니다. OpenCodex가 기존 자격 증명 저장을 소유합니다. 기존 공급자의 파일/환경 변수 키 참조도 유지합니다. SSH 계정 암호·호스트 키 확인과 OS 권한은 자동 승인하지 않습니다.

REA 패키지 설치는 모든 역분석 백엔드·SDK·Cutter 세션이 준비됐다는 뜻이 아닙니다. 대상 형식에 필요한 별도 도구는 REA의 해당 작업 요구 조건에 따라 준비합니다. Claude Desktop의 로그인·폴더 신뢰·최초 MCP 확인도 새 앱에서 확인합니다.

## 서버에 포함된 준비

서버 역할은 현재 쓰는 **동일 NVFP4 포크·UD-IQ4_XS 모델·Pack**을 재사용하는 복구 경로입니다. 다른 모델이나 일반 엔진으로 대체하지 않습니다.

1. Python 가상환경과 서버 의존성을 준비합니다. Linux는 기존 `tools/bootstrap-linux-server.sh`를 재사용합니다. Windows에서는 필요한 Visual C++ 실행 환경도 설치합니다.
2. NVIDIA 드라이버와 GPU를 조회합니다. RTX 3090 Ti가 하나이면 그 장치를 선택하고, 그렇지 않으면 표시된 번호를 선택합니다. 드라이버가 없거나 재부팅이 필요하면 대기 상태로 남깁니다. 하드웨어 드라이버를 임의 버전으로 교체하지 않습니다.
3. 기존 모델·Pack·MTP·비전 프로젝터를 `~/Strata-data`에 복원하고, 해당 OS의 동일 버전 포크를 저장소의 `forks/sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2/strata-nvfp4`에 복원합니다. `data/expert-profile.bin`도 복원합니다. 필요한 파일이 없으면 정확한 누락 경로를 표시하고 중단합니다.
4. 기존 생성기로 ON/OFF 프로필·개인 API 키를 준비합니다. 키가 있으면 재사용하고 형식이 잘못된 키를 덮어쓰지 않습니다. Windows는 선택 GPU와 루프백 실행 옵션을 사용자 환경 변수에 저장하므로 **새 터미널 또는 재로그인 후** 기존 ON/OFF BAT을 실행합니다. Linux는 선택 GPU를 사용자 설정에 저장하고 기존 ON/OFF `.sh`에서 읽습니다.

이 설치기는 대용량 Pack·MTP의 새 생성이나 검증되지 않은 포크 바이너리 다운로드·다른 OS 바이너리 변환을 수행하지 않습니다. 복구 자료가 없는 순수 신규 서버는 해당 포크의 원본 설치·빌드 절차로 자료를 준비해야 합니다. 파일 존재·명세 크기 확인은 전체 파일 해시·GPU 로딩·성능 검증과 구분합니다. Linux 엔진에는 Windows 바이너리의 크기 명세를 적용하지 않습니다. 모델 실행은 준비 후 기존 ON/OFF 실행기로 합니다.

통합 설치로 준비한 Windows 서버는 `STRATA_SERVER_LOCAL_ONLY=1`로 루프백에만 바인딩하며 LAN 방화벽을 자동으로 열지 않습니다. 기존 사용자의 실행 방식은 통합 설치를 선택하지 않으면 유지합니다. LAN 직접 접속으로 바꾸려면 기존 LAN 방화벽/인증 절차를 따르고 이 옵션도 명시적으로 변경해야 합니다.

## 외부 PC와 이어서 설치

접속 방식은 `이 PC의 서버`, `외부 서버(SSH)`, `이미 열린 SSH 터널` 중 고릅니다. 외부 서버는 SSH와 네트워크/VPN이 먼저 준비되어 있어야 합니다. 이 설치기는 SSH 서버·VPN·공유기·포트포워딩을 설치하거나 공개하지 않습니다.

SSH 선택 시 접속 PC의 `127.0.0.1:18080`을 서버의 `127.0.0.1:8080`에 연결하는 창을 엽니다. 해당 창에서 로그인한 뒤 설치 안내에 따라 이어갑니다. 같은 로컬 포트가 사용 중이면 또 다른 터널을 겹쳐 띄우지 않습니다. OpenCodex는 접속 PC의 `127.0.0.1:10100`에 두며 서버의 프록시를 공개할 필요가 없습니다.

Windows 접속 PC에 OpenSSH 클라이언트가 없으면 해당 선택적 기능 설치를 요청합니다. UAC는 사람이 확인하며 거부·실패하면 연결 단계에서 멈춥니다. SSH 주소에 암호를 넣지 않고 `사용자@서버`만 입력하세요.

재실행 옵션은 `--connection local`, `--connection ssh --ssh-host 사용자@서버`, `--connection forwarded`입니다. SSH 호스트와 연결 방식은 설치 기록에 남기지만 암호·API 키는 기록하지 않습니다. 연결이 끊겼을 때 AI 작업을 자동 중복 실행하지 않습니다.

기록은 `~/.config/strata/integrated-install.json`, 동시 실행 잠금은 같은 폴더의 `integrated-install.lock`입니다. 실제 설정 변경 백업은 기존 Claude/OpenCodex 소유자의 경로에 남습니다. 원래 지침이 수동 변경되어 있으면 기존 보호 장치가 중단하며 전체 파일로 덮어쓰지 않습니다. 기존 서비스 충돌도 자동 repair/restart로 해결하지 않습니다.

## 완료 표기의 의미

`설치·연결 설정 완료`는 공통 연결과 Desktop 프로필의 저장 진단을 통과했다는 뜻입니다. 실제 새 앱의 로그인·MCP 실행·GUI 입력·장시간 모델 작업·외부 네트워크 안정성은 각 환경에서 확인해야 합니다. `설치 대기`는 성공이 아니며 표시된 단계부터 이어갑니다.

공식 원문: [OpenCodex 설치](https://opencodex.me/getting-started/installation/), [Claude 다운로드](https://claude.com/download), [CUA 설치·OS 권한](https://cua.ai/docs/cua-driver/quickstart), [Homebrew 설치](https://brew.sh/).


## 2026-10-29 검증 기록

- 기존 unittest 체계에서 설치·복구 계약 27개 통과(1.295초). 설치기 계획의 무변경, 기존 설치 재사용, 실패/불확실한 결과의 재개, 동시 실행 잠금, 자격 증명 비노출, 기존 공통 지침 재사용, 서비스 충돌 차단, SSH 주소 검증, API 키 보존, 정확한 서버 복구 자료 누락 차단, GPU 선택·기존 Linux 준비 경로를 확인했다. 실제 설치·서비스·네트워크 작업은 모의 또는 임시 파일이다.
- 새 셸 3개와 Windows PowerShell 부트스트랩 문법 통과. Windows BAT에서 접속 PC·서버의 --plan 실행 각각 종료 0. 실제 Claude·MCP·OpenCodex 설정의 전후 해시가 같고 설치 기록이 새로 생기지 않았다.
- 첫 Windows 계획 실행은 운영 Strata 가상환경 탐색 누락으로 부트스트랩 계획만 표시했다. 기존 사용자 Strata 가상환경도 탐색하게 보완한 뒤 Python 본문의 전체 계획 출력을 확인했다.
- 새 PC/초기화된 Windows 전체 설치, 실제 Apple Silicon Mac·Linux NVIDIA 설치, 패키지 다운로드/설치, GUI·OS 권한, 외부 SSH, 대규모 모델 로딩·성능은 미검증이다. 원래 앱과 서버는 재시작하지 않았다.

초기 소스 백업: `~/.claude/backups/strata-opencodex-20261028T151908885144Z/files.json`. 후속 보완 백업도 같은 폴더 아래 게시 영수증으로 남았다. 설치기는 광범위한 새 테스트 프레임워크·별도 모델·서버 관리자·프록시를 만들지 않고 기존 소유자의 설정·서비스·실행기를 재사용한다.


배포 보완: 기존 Windows 실행기의 이미지 설정 보존 검사 1개도 통과했다(관련 검사 합계 28개). 외부 PC로 옮길 설치 전용 ZIP을 준비했으며 개인 설정·API 키·모델·Pack·엔진·가상환경은 포함하지 않는다. 첫 ZIP 해제 검증은 샌드박스 임시 폴더의 PermissionError로 실패했다. 허용된 작업 폴더에서 다시 생성·해제하여 파일 해시, 공통 모듈 import, 설치 본문의 --plan 통과를 확인했다. ZIP의 POSIX 셸 실행 권한 메타데이터도 확인했다. Windows 한글 경로의 Python 탐색 인코딩을 UTF-8로 맞춘 뒤 BAT 계획 모드를 다시 확인했다.

## 선택형 서버 자동 업데이트

Windows 서버 설치 후 `SETUP-STRATA-UPDATES.bat`에서 안정판 자동 업데이트를 켤 수 있다. 기본 설치가 임의로 새 포크를 내려받지는 않는다. [자동 업데이트 안내](STRATA_FORK_AUTO_UPDATE_KO.md)를 따른다.
