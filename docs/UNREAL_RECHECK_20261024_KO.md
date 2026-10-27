# Unreal 재검증 — 2026-10-24 KST

## 현재 설치와 범위

이번 재검사에서는 `C:/Program Files/Epic Games/UE_5.8`의 실제 Editor·UBT·UAT·Build.version이 존재했다. Build.version은 **5.8.4**, changelist 58902052다. 앞선 검사에서는 플러그인만 보였으나 현재 실행 가능한 설치로 바뀌었다. 재설치/다운로드나 엔진 바이너리 수정을 수행하지 않았다.

격리 프로젝트와 모든 로그: `C:/Users/luiny/Strata-data/diagnostics/unreal-recheck-20261024-122821`.

## 실제 결과

| 항목 | 결과 | 근거 |
|---|---|---|
| C++ Editor 빌드 | PASS, 62.30초 | UBT Succeeded, 실제 모듈 DLL/UHT 생성 |
| Editor Python | PASS, 10.574초 | exit0, AGENT_UNREAL_EDITOR_PASS |
| Blueprint/레벨/액터 | PASS | C++ 부모 Blueprint 생성·저장, 레벨 언로드/재로드, 액터 값42 확인 |
| 프로젝트 Automation Test | PASS 1/1 | Strata.Probe.ActorDefault, JSON succeeded1/failed0 |
| Windows BuildCookRun | PASS, 약111초 | Development build/cook/stage/pak/IoStore/package/archive, UAT exit0 |
| 패키징된 실행 파일 | PASS, 2.776초 | 실제 실행, /Game/AgentProbeMap의 C++ BeginPlay, 값42 확인, exit0 |

런타임 성공 표식은 `AGENT_UNREAL_RUNTIME_PASS value=42`다. 루트 bootstrap의 종료 코드만 본 것이 아니라 실제 Binaries/Win64 실행 파일과 런타임 로그를 검사했다. `.uasset`·`.umap`은 에디터 API로만 생성했다.

MSVC 14.50.35739 도구 체인(설치 디렉터리14.50.35717), Windows SDK10.0.22621.0, 엔진 내장 .NET10을 실제 사용했다. 시험용 빌드는 동시 action2로 제한했다. 원래 모델/GPU/압축/추론 설정을 바꾸지 않았으며 전역 OpenCode JSON 해시도 이전 적용 기록과 같았다.

## 발견한 언어 의존 검사 오류

첫 한국어 Automation 실행은 프로젝트 검사1개가 성공했지만 엔진 초기 검사에서 `Condition failed` 오류15줄과 레이아웃 호환 경고1줄이 있었다. exit0 또는 프로젝트 JSON만으로 전체 엔진 오류가 없었다고 판단하면 안 된다.

설치 소스 `Engine/Source/Runtime/Core/Tests/Experimental/UnifiedError/UnifiedErrorTests.cpp`는 `CreateErrorMessage` 등의 번역 가능한 결과를 영어 리터럴과 비교한다. 원본 로그에는 같은 메시지가 한국어로 출력됐다. 동일 프로젝트/명령에 **시험 프로세스만 `-culture=en`**을 추가한 재실행은 프로젝트1개 성공, 실패0, 원시 로그 Error 줄0이었다. 이 비교로 초기 오류는 엔진 검사와 실행 언어의 의존 문제로 판단한다. 엔진 자체의 한국어 검사 결함을 패치한 것은 아니다.

원본 `automation-a-*`와 `automation-report/index.json`, 재검사 `automation-en-b-*`와 `automation-report-en/index.json`을 모두 보존했다. 초기 오류/레이아웃 경고를 성공 재검사로 덮어쓰지 않았다. 사용자의 전역 UI 언어와 OpenCode 한국어 보고 설정은 변경하지 않았다.

Unreal 프로젝트 지침에 테스트 수/구조화 결과/원시 로그 확인, 엔진 자체 검사와 프로젝트 검사 구분, 언어 고정 시험에 한정한 프로세스별 언어 지정 규칙을 추가했다. 실제 한국어 UI/현지화 테스트는 대상 언어를 유지해야 한다.

## 실행 경로

- `Build.bat AgentUnrealProbeEditor Win64 Development -Project=... -WaitMutex -NoHotReloadFromIDE -MaxParallelActions=2`
- `UnrealEditor-Cmd.exe ... -run=pythonscript -script=editor_probe.py -nullrhi -unattended`
- `UnrealEditor-Cmd.exe ... -ExecCmds="Automation RunTests Strata.Probe" -TestExit="Automation Test Queue Empty" -ReportExportPath=... -nullrhi -unattended` (언어 고정 비교 재검사에만 `-culture=en` 추가)
- `RunUAT.bat BuildCookRun -Project=... -Target=AgentUnrealProbe -Platform=Win64 -ClientConfig=Development -NoCompileEditor -SkipBuildEditor -Build -Cook -Map=/Game/AgentProbeMap -Stage -Pak -IoStore -Package -Archive -ArchiveDirectory=... -NoDebugInfo -Unattended -NullRHI`

전체 인자와 결과는 editor/automation/runtime result JSON 및 `package-a.log`에 있다. Python은 에디터 자동화이고 게임 플레이용 Python 런타임을 구성한 것이 아니다. [Epic Python 문서](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python), [UAT BuildCookRun 문서](https://dev.epicgames.com/documentation/en-us/unreal-engine/build-operations-cooking-packaging-deploying-and-running-projects-in-unreal-engine)의 경로와 설치 버전 API를 대조했다.

## 아직 검증하지 않은 것

NullRHI로 렌더링을 끈 최소 시험이다. 실제 화면·조작·아트·캐릭터·애니메이션·UMG·성능·멀티플레이·모바일/콘솔·Rider 디버거/GUI 연동을 검증하지 않았다. Blueprint 생성과 C++ 부모 연결은 확인했지만 임의의 복잡한 Blueprint 이벤트 그래프 자동 생성까지 증명하지 않는다. 엔진 한국어 자체 검사 결함은 별도 남은 문제다. 이번 결과는 OpenCode가 엔진 CLI를 사용할 수 있는 로컬 실행 기반의 증거이며 모델이 상용 게임 전체를 무오류 제작한다는 보장이 아니다.

이번 변경은 Unreal 프로젝트 지침과 검증 보고서뿐이다. 사용자 프로젝트/모델/서버는 수정하지 않았고 커밋·푸시는 수행하지 않았다. 실제 결과는 `summary.json`에 모았다.
