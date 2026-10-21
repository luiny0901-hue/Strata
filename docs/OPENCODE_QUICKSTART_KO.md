# Strata + OpenCode + CUA: 복원과 외부 PC 사용

## 한 곳에서 가져오기

기존 서버/클라이언트/CUA 설정 브랜치를 다음 브랜치에 합쳤습니다. 새 PC에서는 이 브랜치를 받습니다. 기존 작업 폴더 위에 덮어쓰지 마세요.

```sh
git clone --branch feature/opencode-session-recovery https://github.com/luiny0901-hue/Strata.git Strata
cd Strata
```

모델·팩·실행 바이너리·비밀 키·개인 설정 백업은 Git에 없습니다. 서버를 초기화할 때는 `Strata-data`와 필요한 로컬 비밀정보를 따로 안전하게 보관하고, 아래 서버 복원 문서에서 고정된 버전과 해시를 확인합니다. Git clone만으로 모델 서버가 설치되지는 않습니다.

## 이 PC에서 계속 사용

현재 서버의 ON/OFF BAT, CPU 비전, 262144 context 상한, 이미지 1024 token 설정은 유지합니다. 두 BAT 중 하나만 실행합니다.

- `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat`
- `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.bat`

이번 클라이언트 개선은 서버 재시작을 요구하지 않습니다. 진행 중인 일을 안전하게 끝낸 뒤 OpenCode 세션을 새로 시작해 MCP와 지침을 다시 읽습니다. 기존 글로벌 설정을 업그레이드하는 명령:

```powershell
py -3 tools/configure_opencode_session_recovery.py
py -3 tools/configure_opencode_cua_automation.py
```

설치기는 기존 provider·키·모델·개인 지침을 보존하고 변경 파일 옆에 백업합니다. Node.js와 CUA Driver가 설치되어 있어야 합니다. 잘못된 명시 경로나 알 수 없는 기존 GUI 정책은 덮어쓰지 않습니다.

UAC 확인 창은 운영체제 보안 데스크톱이므로 에이전트가 누르지 않습니다. 관리자 권한이 필요한 작업은 `BLOCKED_UAC`로 끝나며, 사용자 본인이 승인하거나 제시된 단일 관리자 명령을 실행한 뒤 결과를 새 요청으로 전달합니다. 승인 대기·반복 시도·권한 우회는 하지 않습니다. 수락 조건이 모두 검증된 작업은 최종 답변으로 끝나며 이후 도구 호출을 계속하지 않도록 지침과 정책을 함께 적용합니다.

## 새 Windows / Apple Silicon Mac 클라이언트

1. Python 3.10+, Node.js, OpenCode V2를 해당 PC에 설치합니다. Windows의 제한 시간 셸 도우미는 PowerShell 7, Mac의 Bash 도우미는 GNU `gtimeout`이 필요합니다. 기본 macOS에는 `gtimeout`이 없을 수 있습니다.
2. Windows: `SETUP-OPENCODE.bat` 더블클릭. Mac: `sh setup-opencode.sh`.
3. 서버 주소와 API 키를 입력합니다. 같은 서버 PC는 `127.0.0.1:8080`, 외부 PC는 서버의 LAN/Tailscale 주소를 사용합니다. `/health`와 `/v1/models`에서 실제 모델과 context를 읽습니다.
4. CUA가 없으면 설치기가 공식 설치 동의를 묻습니다. CUA는 화면을 조작할 클라이언트에 설치됩니다. Mac의 화면 기록·손쉬운 사용 권한은 직접 승인해야 합니다.
5. REA 등록 여부를 묻으면 기본 선택을 수락하세요. 권한 있는 실행 파일·DLL·설치 프로그램·APK·Electron/ASAR 등 바이너리 아티팩트의 분석·검사·역공학·비교 요청은 `rea_analysis` subagent가 자동 선택됩니다. REA는 일반 코딩 세션에서는 비활성이라 도구 컨텍스트를 불필요하게 늘리지 않습니다.
6. Windows는 `SETUP-OPENCODE.bat run`, Mac은 `sh setup-opencode.sh run`으로 실행합니다. 저장된 wrapper가 생성 overlay를 지정합니다. Rider는 재시작 후 등록된 `OpenCode Strata`를 선택하세요. 기존 글로벌·프로젝트 설정과 병합되므로 프로젝트별 덮어쓰기 여부는 확인해야 합니다.

이 경로는 세션 복구, REA 전용 분석 subagent, 기본 200단계 작업 예산(사용자 지정값 보존), 자동 압축(선택 모델 context의 1/8 최근 보존과 1/4 여유, 각각 최대 12000/65536), 제한 시간 셸 도우미, 짧은 한국어 지침, 창 단위 CUA 중계기를 함께 설치합니다. 현재 사용자 계정에서 OpenCode 도구 권한은 전체 허용이므로 파일·셸·Git·외부 폴더·MCP 작업에 승인 대화가 없습니다. 기존 `setup`을 다시 실행해도 synthetic 설정 테스트에서 ACP 항목이 중복되지 않았습니다. 개별 파일은 백업 후 원자 교체하지만 전체 설치가 한 트랜잭션은 아닙니다. 오류가 나면 출력 원인을 수정한 뒤 setup을 재실행하고 doctor를 확인합니다.

지침은 기존 설계·기능 소유자·테스트를 재사용하고 변경의 영향 범위에 맞는 검증을 요구합니다. 필요한 플랫폼 어댑터나 API를 코드 유사성만으로 합치지 않습니다. 필요한 검증을 할 수 없으면 미실행과 한계를 보고합니다. 이 공통 지침은 특정 언어의 정적 분석기를 대신하지 않으므로 저장소별 구조 검사는 프로젝트에서 별도로 제공해야 합니다.

`SETUP-OPENCODE.bat doctor` 또는 `sh setup-opencode.sh doctor`는 접속·설정 진단입니다. 실제 Rider/Hermes/GUI 동작이나 장기 작업 완료를 입증하지 않습니다. 이 작업에서는 Rider/Hermes 검증을 수행하지 않았습니다. Hermes는 별도의 에이전트 설정을 사용하며 OpenCode 설정이 자동으로 복사되지 않습니다.

## 지연을 줄이는 방식과 경계

- 설치 안내 전체를 모델 instructions에 넣지 않고 짧은 작업 규칙만 넣습니다.
- CUA 창 목록을 불필요하게 반복하지 않고, 접근성 트리가 충분하면 `since`와 스크린샷 없는 상태 읽기를 사용합니다. 빈 트리·캔버스·불확실한 결과는 화면으로 확인합니다.
- 화면 입력은 background만 허용하며 foreground 재시도·사용자 마우스·전역 입력·GUI 앱 자동 실행은 차단합니다. 기본 스크린샷 상한 1920px은 중계기가 전달하며 명시적 크기 요청은 보존합니다.
- CUA catalog 프로세스 종료/실행 실패를 즉시 오류로 전달합니다. 실패한 입력을 자동 재실행하지 않습니다.
- 262K는 상한이며 매 요청을 채우라는 목표가 아닙니다. 관련 파일부터 읽고, 장기 작업은 단계별 검증·인계로 이어갑니다. 자동 도구 선택은 모델 지침이며 무오류·무한 작업 보장이 아닙니다.
- 이번 변경의 실제 모델 prefill/decode·전체 GUI 완료 시간은 측정하지 않았습니다. 서버 추론 예산·GPU·모델을 바꾸지 않았습니다.

## 서버 복원 / 네트워크

- [고정 NVFP4 + IQ4_XS 서버 복원](IQ4XS_NVFP4_OPENCODE_SETUP.md)
- [LAN·Tailscale 및 플랫폼 경계](REMOTE_AGENT_CLIENTS_KO.md)
- [클라이언트 상세 설정](../tools/remote_agent_client/README_KO.md)
- [Unreal Engine · Unity 프로젝트 지침](GAME_ENGINE_OPENCODE_KO.md)

BAT은 Windows 전용입니다. Linux 서버는 자체 설치·방화벽·GPU 경로를 별도 확인해야 하며 이 작업에서 실행하지 않았습니다. 서버를 공용 인터넷에 직접 공개하지 마세요. 키 인증과 Private LAN/Tailscale 제한을 유지합니다. 기존 LAN 방화벽의 공백 포함 프로필 판정/Tailscale 처리는 복원 브랜치에 함께 보존했으며 이번 작업에서 실제 방화벽을 변경하지 않았습니다.
