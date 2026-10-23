# 새 PC 자동 준비

명령어 없이 시작하려면 Windows는 루트의 **START-AGENT.bat**, Mac은 **START-AGENT.command**를 여세요.
**처음 설정 → 사용 시작 → 연결 문제 확인** 메뉴를 제공합니다.
[일반 사용자 안내](../START-HERE-AGENT-KO.md)를 먼저 읽으세요.

이 경로는 오프라인 테스트를 수행했습니다. 실제 새 PC 설치·원격 추론·Mac/Linux 실기 검증은 하지 않았습니다.
[검사 결과와 실패 이력](AGENT_SETUP_VALIDATION_KO.md)을 참고하세요.

## 외부 Windows / Apple Silicon Mac

Git이 없으면 GitHub의 해당 브랜치에서 Code → Download ZIP으로 받아 압축을 풀어도 됩니다.
브랜치는 `feature/opencode-session-recovery`입니다. 저장소 루트에서:

| OS | 처음 설치 | 평소 사용 |
|---|---|---|
| Windows | `SETUP-OPENCODE.bat` 더블클릭 | `SETUP-OPENCODE.bat run` |
| Apple Silicon Mac | `sh setup-opencode.sh setup` | `sh setup-opencode.sh run` |

`setup`만 부족한 선행 프로그램을 설치합니다. `run`과 `doctor`는 패키지 설치를 하지 않습니다.

- Windows: winget으로 Python 3.12, Node.js LTS, PowerShell 7 설치. winget 자체가 없으면 Microsoft Store의 App Installer 설치 후 재실행 안내.
- Mac: 공식 Homebrew 설치기, Python 3.12, Node.js 24, coreutils를 필요한 경우 설치.
- OpenCode가 없으면 공식 V2 패키지 `@opencode/cli@2.0.22` 설치. 기존 OpenCode를 자동 교체하지 않으며, V1이면 기존 설정기의 V2 안내로 중단.
- 기존 Node가 REA 지원 버전보다 오래되면 자동 교체하지 않고 업그레이드 안내 후 중단.
- 선행 설치가 끝나면 서버 주소·API 키 입력 → CUA 설치 선택 → REA 등록 선택으로 이어짐.
- CUA·REA 선택 기본값은 설치/등록. Mac 화면 기록·손쉬운 사용과 OS 관리자 승인은 직접 처리.
- Mac Rider용 wrapper에도 Homebrew Node/Python 및 사용자 OpenCode 경로 적용.

실패하면 오류를 해결한 뒤 같은 `setup`을 재실행합니다. 기존 설정 백업과 키 보존은 기존 설정기를 따릅니다.
현재 실행 중인 서버에 연결하는 클라이언트 설치 과정이며 서버 모델은 받지 않습니다.

## Linux 서버

```sh
sh SETUP-LINUX-SERVER.sh --mode on
```

Ubuntu/Debian 또는 dnf 배포판에서 Python/venv/pip가 없으면 패키지 관리자로 설치하며 sudo 승인이
필요할 수 있습니다. 저장소 전용 `.venv`를 만들고 저장소의 고정 requirements를 설치한 뒤
프로필과 API 키를 준비합니다. 이미 존재하는 불완전한 환경을 삭제하지 않습니다.

동일 NVFP4 포크의 Linux 엔진·서버 코드·추가 의존성·모델·팩·MTP는
[Linux 서버 안내](LINUX_NVFP4_SERVER_KO.md)에 따라 별도로 준비해야 합니다.
이 단계는 완전 자동 모델 서버 설치나 실행 성공 확인이 아닙니다.
Windows 서버의 엔진/모델 복원도 기존 [서버 복원 안내](IQ4XS_NVFP4_OPENCODE_SETUP.md)를 따릅니다.

공식 설치 방식 참고: [OpenCode V2](https://dev.opencode.ai/v2/docs),
[Homebrew](https://docs.brew.sh/Installation.html).
