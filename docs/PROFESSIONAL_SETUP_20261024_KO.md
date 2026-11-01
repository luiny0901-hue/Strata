# 전문 소프트웨어·게임 개발 환경 적용 보고서 — 2026-10-24

## 1. 실제 환경

| 구성 | 확인 결과 |
|---|---|
| 소스 / 실행 파일 | `C:/Users/luiny/Strata-opencode-session-recovery` / `C:/Users/luiny/Strata` |
| 실행 Strata 엔진 | API 응답 `0.1.44.1`, OpenAI 호환 `/v1/chat/completions` |
| 모델 | Qwen3.8-Flash-Next Unsloth UD-IQ4_XS, 기존 NVFP4 fork 프로필 |
| 컨텍스트 / 동시 생성 | 262,144 / 1 슬롯 |
| GPU / 메모리 | 모델 GPU는 RTX 3090 Ti. 조사 표본 VRAM 약 23,530 MiB, 시스템 전체 RAM 약 93.5 GiB. 둘 다 전체 장치/시스템 표본이며 모델만의 할당량이나 상한 증거가 아니다. RTX 3090은 모델용으로 추가하지 않았다. |
| OpenCode | 실제 설치 2.0.22, `build`, 512 steps, 기존 provider/model |
| 압축 | auto, keep 12,000, buffer 65,536 유지 |
| Rider | product-info 기준 2026.2.3.1, build 262.10968.170. 설치 폴더명 2026.2.0.2와 다르다. |
| .NET / C++ | SDK 10.0.302·10.0.401, vswhere에서 VC.Tools.x86.x64 포함 VS Community 2026 확인. Rider 언어 서비스·C++ 디버깅은 별도 미검증. |
| Unity | 6000.5.7f1 실제 Editor 실행·빌드·플레이어 실행 통과 |
| Unreal | 앞선 검사 후 설치 상태가 바뀌었다. 재검사에서 5.8.4 C++/Editor/Automation/Windows 쿠킹·패키징·실행 통과. 아래 재검증 기록 참고. |
| MCP | 구성된 CUA 초기화/18개 도구, REA 초기화/207개 도구 목록 수신. 실제 클릭·역공학 수행 검증은 아니다. |

증거 루트: `C:/Users/luiny/Strata-data/diagnostics/professional-setup-20261024/`.
`environment.json`은 필요한 공개 구성만 저장했다. API 키는 기록하지 않았다.

## 2. 발견한 문제와 수정

- 전문 제품에 대한 기술 선택이 흔들렸다. 초기 응답에 복수 스택/지원 OS 혼동과 근거 없는 .NET 8 고정이 있었고, 첫 보완 후에는 이미지 편집기에 확장 편의를 이유로 Electron을 선택했다. 전문 편집·CAD의 처리/메모리/지연 파이프라인을 먼저 비교하고 하나의 주 선택, 지원 OS와 미확인 버전을 명시하도록 보완했다.
- 구조 선택 시험에서 none 추론은 기능별 파일을 반복 나열해 1,000 토큰에 잘린 응답 3개와 Unity 버전을 Unreal에 붙인 오류를 보였다. 제품별 버전 근거 분리·소유 모듈 중심 구조 규칙을 추가했다. 최종 High 시험은 다섯 개 모두 정상 종료와 올바른 제품 계열을 확인했지만 모든 추론 강도/입력에서 오류가 사라졌다는 보장은 아니다.
- 한국어 Windows에서 UTF-8 모드의 ACL 조회가 디코딩 오류로 실패했다. whoami/icacls를 OEM 인코딩으로 읽도록 수정했다. 판독 불가능한 권한을 허용하는 변경은 아니다.
- 기존 엔진 전용 생성기에 전문 데스크톱 템플릿이 없었다. 비덮어쓰기 동작을 재사용해 `--profile desktop`을 추가했다.
- Unreal 폴더 존재만으로 실행 가능한 설치로 간주하면 잘못된 완료 보고가 된다. 실행·빌드 도구 부재를 명시했으며 대규모 다운로드나 재설치를 하지 않았다.

기존 지침과 설치 소스에서 HTML을 강제하는 원인은 확인하지 못했다. 모델의 선택 편차는 재현했으나 Rider/OpenCode 코어가 원인이라고 단정하지 않는다.

## 3. 적용 파일과 유지 항목

| 파일 | 변경 |
|---|---|
| `examples/opencode/KOREAN_INSTRUCTIONS.md` | 실제 엔진/데스크톱, 요구 기반 스택·역할·버전/구조 선택 보완 |
| `examples/opencode/professional/DESKTOP_AGENTS.md` | 전문 데스크톱의 데이터·명령·UI·렌더·파일 경계와 검증 |
| `examples/opencode/game-engines/UNITY_AGENTS.md` | 필요한 역할 관점과 기능/에셋/플레이/성능/배포 결과 구분 |
| `examples/opencode/game-engines/UNREAL_ENGINE_AGENTS.md` | Unreal 전용 규칙 안에서 같은 결과 구분 |
| `tools/install_engine_project_guidance.py` | desktop/unity/unreal `--profile`, 기존 `--engine` 호환, 기존 AGENTS.md 보존 |
| `tools/remote_agent_client/setup_client.py` | ACL 디코딩 수정, 설치 revision 14 |
| `tools/test_engine_project_guidance.py`, `tools/test_remote_agent_client.py` | desktop 경로 검사, 오래된 문구 검사 보정, 개인 프로필과 일반 설치 시험의 격리 |
| `docs/GAME_ENGINE_OPENCODE_KO.md`, client README, 이 보고서 | 사용법·실제 검증 범위 |

전역 OpenCode JSON, ACP 등록, 모델·추론 기본 High·출력 32,000·GPU·캐시·권한·압축 설정은 유지한다. 현재 PC의 한국어 지침은 기존 내용 일치 확인과 백업 후 갱신한다. 개인 portable-profile은 세 지침 중 해당 문서만 교체하고 나머지 설정을 보존한다. 실행 중 서버/Rider를 강제 재시작하지 않으며 새 OpenCode/ACP 연결에서 새 지침을 사용한다.

## 4. 에이전트와 Skills

메인 `build`가 요구·구현·통합을 소유한다. 설계, 게임 시스템, 그래픽/에셋, QA는 현재 작업에 필요한 관점만 적용한다. 별도 전문가 호출·새 병렬 세션·보고서 생성을 매 작업 강제하지 않는다. 단일 모델 슬롯에서 불필요한 다중 호출을 늘리지 않았다.

새 상시 MCP/Skills를 추가하지 않았다. 일반 소스는 기본 도구, 필요한 실제 GUI는 기존 CUA, 바이너리 분석은 기존 `rea_analysis` 경로를 사용한다. 일반 build에는 `rea_*` 도구가 숨겨져 있어 REA 전체 목록을 매 요청 주입하지 않는다. 등록/도구 목록 확인과 실제 기능 검증은 구분한다. 전문 프로젝트 상세 규칙은 저장소의 AGENTS.md로 제공한다.

OpenCode V2 [에이전트 공식 문서](https://opencode.ai/v2/docs/agents)와 JetBrains [ACP 공식 문서](https://www.jetbrains.com/help/ai-assistant/acp.html)를 로컬 2.0.22 소스/설정과 대조했다. `agents.build`, 별도 기존 REA subagent, `.jetbrains/acp.json`의 command/args/env 경로를 보존했다.

## 5. 엔진별 실제 지원 상태

| 작업 | Unity 6000.5.7f1 | Unreal |
|---|---|---|
| 격리 프로젝트/Editor Script | PASS | PASS — 5.8.4 C++/Python |
| Scene·Prefab / Unreal Level·Actor·Blueprint 저장·재조회 | PASS | PASS |
| Windows Development Build | PASS | PASS |
| 빌드한 플레이어 NullRHI/렌더링 없는 실행·객체 검사·정상 종료 | PASS | PASS |
| EditMode/PlayMode / Unreal Automation | NOT_RUN | PASS 1개; 한국어 엔진 초기 검사 오류 별도 기록 |
| 실제 UI·애니메이션·캐릭터·셰이더·아트 품질 | NOT_RUN | NOT_RUN |
| Windows 쿠킹·패키징 | 위 Windows 빌드 | PASS |
| 모바일/콘솔·실기 | NOT_RUN | NOT_RUN |

Unity 증거는 `unity.log`, `unity-build.log`, `unity-player-build.log`, `unity-player-run.log`와 각 result JSON이다. 이전 Editor 실행 로그의 debugger/종료 경고도 보존했다. 성공은 exit 0, 실제 산출물, 명시적인 검사 marker로 판정했다. 마지막 플레이어는 `GameObject.Find("AgentProbe")`를 확인하고 직접 종료한다. 창·그래픽/플레이 품질 검수가 아닌 최소 런타임 시험이다.

Unreal에는 완전한 해당 버전 Editor·UBT/UAT·지원 C++ 툴체인이 필요하다. 현재 Blueprint/레벨/에셋/Editor Python/쿠킹/패키징 가능 여부는 미검증이며 소스 템플릿만으로 검증됐다고 하지 않는다.

## 6. 전문 데스크톱 지원

desktop 지침은 요구 OS·대용량/정밀도·GPU/지연·파일 호환성을 확인하고 문서/명령·undo/redo·선택/도구·UI·작업 스레드·렌더·파일 입출력 소유권을 제품에 맞게 둔다. 반응성·저장 실패·취소·메모리·마이그레이션·배포를 실제 범위에 맞춰 검증한다. 무조건적인 플러그인 프레임워크나 수십 개 manager를 요구하지 않는다.

이번 실제 편집/실행 시험은 .NET 콘솔의 작은 계산 수정이다. Photoshop/CAD/영상 편집 수준의 UI·대용량 렌더링·정밀도·플러그인 ABI를 구현하거나 검증한 결과는 아니다. Qt SDK 실행 가능 버전도 아직 미확인이다.

## 7. 추론·출력 설정

기존 선택지는 none/low/medium/high다. 설치 Strata frontend는 high를 모델 템플릿 xhigh로 매핑하고 none은 thinking을 끈다. 별도의 미지원 Extra High UI를 추가하지 않았다. 기존 프로필과 출력 상한 32,000은 변경하지 않았다. 시험 전용 budget은 아래와 구분한다.

`effort-probes.json`: 네 강도로 실제 `17+25`를 호출해 모두 42/정상 stop을 확인했다. 시험에만 출력 1,024와 budget 8,192를 전달해 작은 출력에서도 답변이 나오는지 확인했다. 서버 소스는 budget이 출력 한도에 너무 가까우면 답변 영역을 남기도록 낮춘다. 정확한 내부 budget 수치의 실행 로그 계측이나 네 강도의 코딩 품질 비교는 아니다.

도구 잘림 복구·중복 완료 방지·취소 스트림·캐시를 유지하는 압축은 기존 보완을 재사용했다. 이번 Node 28개 회귀 검사가 통과했다. 이전 실제 취소·약9만 토큰 압축 비교는 `LONG_AGENT_REPAIR_20261024_KO.md`와 `CONTEXT_CACHE_REPAIR_20261024_KO.md`에 별도 실패 이력과 한계가 있다. 이번 작업에서 262K 장시간 프로젝트 전체를 다시 시험한 것은 아니다.

## 8. Rider·OpenCode 실제 연결

사용자가 Rider에서 격리 프로젝트를 열고 읽기 전용 요청을 전송했다. 실제 OpenCode DB 세션 `ses_e94928af0ffeSz50itpPHFj5TD`에서 Strata 모델/High/build, Program.cs·KEEP.txt read 도구 완료, 내용에 맞는 한국어 최종 설명과 succeeded/idle을 확인했다. 파일 편집 도구는 호출되지 않았다. 증거는 `rider-session-snapshot.json`, `rider-messages.json`이다.

별도 실제 설치 OpenCode ACP+동일 Strata의 격리 시험에서는 Add의 뺄셈 오류를 덧셈으로 고치고 실행한 뒤 같은 세션의 후속 수정까지 통과했다. 도구가 실행 결과를 읽었으며 독립 실행 검사도 통과했다.

- 첫 요청: 21+21=42; 독립 입력 6,8 출력 14.
- 후속 요청: Add는 보존하고 출력에 +1; 21,21 출력 43; 독립 입력 6,8 출력 15.
- KEEP.txt 보존, 최종 서버 idle.

`live-acp/results.json`과 events에 기록했다. 이 편집 시험은 Rider GUI 입력이 아닌 같은 실제 ACP 경로다. 현재 Codex의 네이티브 GUI 제어가 비활성화돼 Rider 채팅/중지 버튼을 직접 클릭한 검증은 하지 않았다. 언어 서비스·디버거·화면 완료 버튼 동기화도 이번 검증 범위 밖이다.

## 9. 다섯 기술 선택 시험과 실패 이력

| 요청 | 최종 High + 환경 근거 + 핵심 모듈 시험 |
|---|---|
| 고품질 3D 액션 RPG | Unity C#/HDRP, Windows 빌드, Core/Player/Combat 등 |
| Unreal 오픈월드 | Unreal 5 C++/Blueprint, 정확 버전 미확인·불완전 설치 명시 |
| Unity 모바일 RPG | Unity C#/URP, 모바일 경로, 실기/SDK 확인 필요 |
| 전문 이미지 편집기 | C++20/Qt6, 문서·이미지 처리·UI·렌더·테스트 등 |
| Windows 하드웨어 모니터 | C#/.NET10/WPF, 플랫폼 수집·UI·저장·테스트 등 |

최종 다섯 개는 JSON 파싱/stop/실제 제품 계열/8개 이하 핵심 구조를 확인했다. 패키지·렌더 파이프라인·플러그인 필요성은 실제 프로젝트에서 별도 판단해야 하며 응답의 모든 제안이 최적이라는 의미는 아니다.

기록을 덮어쓰지 않았다:
1. `stack-selection.json`: 최초 none 5개, 스택/OS/버전 설명 일부 부정확.
2. `stack-selection-recheck.json`: 첫 수정 후 none 2개, Electron 편의 선택·미확인 .NET8 잔존.
3. `stack-selection-final.json`: 전문 제품 규칙/실제 환경 추가 후 none 2개. 데스크톱 방향은 개선됐지만 최종 검증으로 단독 채택하지 않았다.
4. `stack-selection-final-five.json`: 구조도 묻자 none에서 3개 length/반복·Unreal 버전 혼동 발생.
5. `stack-selection-reviewed-five.json`: 제품별 버전·모듈 규칙 보완, High 및 시험 전용 budget640/max1800, 핵심 모듈 최대8 요청, 5개 정상 완료.

정책·입력 조건·추론 강도를 함께 보완했으므로 지침만으로 개선됐다고 인과를 단정하지 않는다. 이 결과를 모든 말투·컨텍스트·추론 강도에서의 무오류 보장으로 확대하지 않는다.

## 10. 회귀·배포와 미검증

- 최초 Python 46개: 실패2/오류1. desktop에 게임 전용 단어를 강제한 검사, 오래된 한국어 기대 문구, 실제 ACL 디코딩 문제였다. 첫 출력은 작업 도구 기록에 있으며 b/c/최종 로그는 증거 폴더에 보존했다.
- b: ACL/게임 검사 수정 후 오래된 문구 실패1 유지.
- c 및 final: Python 47개 통과. 실제 한국어·공백 경로의 키 ACL 생성/재쓰기 검사 포함.
- Node: 출력 복구/취소·스트림 수명 검사 28개 통과.
- 배포 후 runtime 폴더의 첫 검사 43개는 실패2/오류1이었다(`regression-deployed.log`). 일반 설치 시험이 runtime의 개인 portable-profile을 읽어 기대값이 달라졌고 portable profile 테스트 모듈도 runtime에 없었다. 일반 설치 fixture를 임시 package로 격리하고 해당 테스트 모듈을 동기화했다. 개인 프로필 자체는 바꾸지 않았다. 소스 재검사 47개 통과(`regression-isolated-source.log`), 반영 후 runtime 재검사는 `regression-deployed-fixed.log`다.
- 압축을 푼 일반/개인 패키지 모두 desktop 지침 생성·기존 파일 덮어쓰기 거부·기존 Unity/Unreal --engine 별칭을 통과했다(`deployed-verification.json`).
- 일반/개인 ZIP은 기존 파일을 백업하고 갱신한다. CRC·핵심 파일 일치와 개인 프로필 분리/설정 보존 기록은 `deployment.json`이다.
- 기존 모델/서버 재설치·방화벽 공개·GPU 재시작·사용자 프로젝트 변경·커밋/푸시는 수행하지 않았다.
- 새 PC 전체 설치, macOS/Linux 실행, 외부 네트워크 접속, Unreal, 실제 상용 제품/게임 품질·성능·장기 무인 운용은 미검증이다.

## 11. 새 프로젝트 시작 방법

현재 PC는 새 OpenCode/ACP 연결부터 갱신 지침을 읽는다. 기존 프로젝트 지침과 최신 사용자 요구가 우선한다. 새 폴더에서 해당 템플릿을 한 번 생성한다:

```powershell
py -3 tools/install_engine_project_guidance.py --profile desktop --project "D:\Apps\MyEditor"
py -3 tools/install_engine_project_guidance.py --profile unity --project "D:\Games\MyUnityGame"
py -3 tools/install_engine_project_guidance.py --profile unreal --project "D:\Games\MyUnrealGame"
```

기존 `--engine unity|unreal`도 동작한다. 폴더가 존재해야 하며 기존 AGENTS.md는 덮어쓰지 않으므로 필요한 항목만 검토해 병합한다. SDK·대상 OS·프로젝트 버전·실제 빌드/테스트 명령은 프로젝트에서 채운다. 다른 PC에서는 갱신 ZIP을 풀고 `SETUP-OPENCODE.bat setup` 또는 `sh setup-opencode.sh setup` 후 `doctor`를 실행한다. 개인 ZIP만 현재 작업/도구/추론 프로필을 포함하며 서버 키·주소·로컬 경로는 그 PC에서 지정한다.

예: “Windows 설치형 이미지 편집 프로그램을 만들어줘. 대용량 레이어 문서와 undo/redo·저장 복구를 우선하고, 요구에 맞는 실제 데스크톱 스택으로 빌드/실행 가능한 범위부터 구현해줘.” 엔진 지정 게임은 Unity/Unreal과 실제 목표 플랫폼·핵심 플레이·품질/성능 기준을 함께 전달하면 된다.


## Unreal 후속 재검증

2026-10-24 사용자 요청으로 다시 확인했을 때 Unreal 5.8.4 설치가 완료돼 C++ 빌드, Editor Python, Blueprint/레벨 저장·재조회, Automation1개, Windows 쿠킹·패키징·실행을 통과했다. 위 초기 미검증 서술은 앞선 시점의 기록이며 현재 상태는 표와 [후속 보고서](UNREAL_RECHECK_20261024_KO.md)를 따른다. 한국어 엔진 자체 검사 오류와 시험 프로세스에만 영어를 지정한 재검사 결과도 그 문서에 보존했다. 실제 그래픽·복잡한 게임 품질·다른 플랫폼은 여전히 미검증이다.


## 엔진과 무관한 비웹 요구 후속 반영

후속 사용자 요청에 따라 웹을 명시하지 않은 새 제품에서는 Electron/Tauri/WebView 포장도 대체안에서 제외했다. Unity/Unreal 미사용·자체 엔진·엔진 없이 개발해도 같은 비웹 규칙을 적용한다. 앞선 기술 선택 시험의 예외 문구는 현재 정책이 아니며 [후속 정책과 검증 한계](NATIVE_OUTPUT_POLICY_20261024_KO.md)를 따른다.
