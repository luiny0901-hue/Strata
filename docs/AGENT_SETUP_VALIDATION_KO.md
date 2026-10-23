# 설치·실행 메뉴 점검 기록 (2026-10-22)

범위: 로컬 오프라인 검사. 실제 설치기, 패키지 다운로드, 운영 설정 변경, GPU 서버 실행,
원격 추론, Rider/Hermes 세션, CUA 화면 입력은 수행하지 않았다.

## 수정

- Linux 키 생성: `Path.open(opener=...)`는 지원되지 않아 최초 준비가 TypeError로 끝났다.
  기본 `open`의 배타 생성과 0600 권한으로 수정했다. 잘못된 키와 디렉터리는 덮어쓰지 않는다.
- Linux: `--python` 지정 시 의존성 설치 대상도 해당 가상환경으로 맞췄다. 시스템 Python에는 pip 설치하지 않는다.
- Windows: PATH 갱신에서 기존 프로세스 경로를 보존했다. 깨진 Python launcher는 다음 후보를 시도한다.
  메뉴 재호출은 현재 PowerShell 실행 파일을 사용한다. Node 설치 뒤 node/npm 존재를 확인한다.
- Mac: Homebrew가 발견된 실제 경로로 shellenv를 실행하고 실패를 전달한다.
  일반 실행에서는 설치하지 않고 기존 Node/Python 경로를 Rider wrapper에도 전달한다.
- Mac `.command`는 LF 줄바꿈으로 고정했다.

## 시도 이력

1. 기존 remote client/REA 테스트 22개 통과. 초기 `bash -n`에 여러 파일을 전달한 검사는 첫 파일만
   읽으므로 전체 문법 검사의 증거로 사용하지 않았다. 이후 각 파일을 개별 검사했다.
2. 새 테스트 포함 31개 시도: Linux 키 생성 TypeError로 2개 오류.
   Windows 메뉴 출력 캡처에서 cp949 디코딩 스레드 오류도 발생했다. 테스트 캡처를 바이트로 바꿨다.
3. 키 생성/테스트 수정 후 31개 통과. 모의 셸 분기 추가 후 57개 통과.
4. Mac 기존 의존성 재사용 테스트 추가 후 58개 통과.
5. Windows 미설정 상태의 실제 bootstrap `run --home 임시폴더` 검사 추가 후 최종 59개 통과.
   설치 없이 종료 코드 2를 반환하고 임시 사용자 폴더에 설정을 쓰지 않았다.

최종 Python 명령:

```text
python -m unittest tools.test_agent_setup_bootstrap tools.test_remote_agent_client tools.test_rea_integration tools.test_opencode_runtime_assets tools.test_opencode_session_recovery tools.test_configure_opencode_cua_automation
```

- Windows 터미널: `python -m unittest tools.test_opencode_terminal_runners` → 11개 통과,
  Linux 전용 클래스 1개 건너뜀(총 Ran 12, skipped=1). 제한 시간·오류·입력 대기 관련 격리 검사.
- `node tools/test_acp_foreground_guard.mjs` → 스크립트의 모든 검사 통과.
- `node tools/test_output_recovery.mjs` → 17개 통과.
- `node tools/cua-driver/opencode-policy.test.mjs` → 9개 통과.
- `node tools/cua-driver/opencode-grounding.test.mjs` → 9개 통과.
- 모든 새 셸 진입점은 Git Bash로 각각 `bash -n` 통과.
- Windows PowerShell 5.1 파서, UTF-8 BOM, 메뉴의 0번 종료 검사 통과.
- Mac/Linux 분기 실행 검사는 Git Bash와 가짜 프로그램을 사용했다. 실제 brew/apt/dnf/npm 설치를
  실행하지 않았으며 플랫폼 동작 성공 증거로 사용하지 않는다.

## 남은 범위

새 Windows PC의 winget/UAC 설치, Mac 실기 권한/설치, Linux 배포판별 의존성 설치와 포크 바이너리,
실제 원격 연결·모델 생성·GUI 입력·전체 작업 완료는 미검증이다.
모델·팩·MTP·엔진 및 GPU 드라이버의 완전 자동 복원은 제공하지 않는다.
이번 변경은 로컬 미커밋 상태이며 푸시하지 않았다.


## 2026-10-23 재설치·외부 접속 갱신
- 원격 setup revision 8: 로컬에서 사용한 MCP 첫 요청 준비 제한 15000ms를 ACP guard에 포함. doctor에서 이전 revision을 안내한다.
- 첫 사용 안내에 로컬/외부 주소 구분, Tailscale 선행 연결, CUA 채팅 승인 범위와 서버 모델·엔진 백업 경계를 명시했다.
- 초기 집중 설치 검사 5개 통과. 새 자산·revision·MCP 준비 설정 검사와 bootstrap 검사 묶음 14개 통과(일부 검사 중복 실행).
- 배포 ZIP 13개 항목 갱신. 무결성과 승인 중계기 등 주요 자산 5개가 소스와 동일함을 확인했다.
- 최초 ZIP 갱신은 ZipInfo 재사용으로 메모리 내 원본 offset이 변해 Overlapped entries 오류가 발생했다. 원본 교체 전에 중단됐다. ZipInfo를 복사하도록 갱신 코드를 수정한 뒤 재생성·검증 후 교체했다. 원본 백업을 보관했다.
- 새 Windows/Mac의 실제 설치, macOS 권한, 외부망 및 Rider 승인 UI 실행은 미검증. 로컬 전용 서버 모델·엔진은 클라이언트 ZIP에 포함하지 않는다.
