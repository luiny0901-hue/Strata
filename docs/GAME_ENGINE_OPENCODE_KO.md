# Unreal Engine · Unity 프로젝트용 OpenCode 지침

이 저장소의 전역 OpenCode 규칙은 장기 코딩·중복 방지·CUA 경계를 다룹니다. Unreal과 Unity에는 엔진 버전, 에셋 직렬화, 빌드·테스트 명령처럼 프로젝트마다 달라지는 추가 지침이 필요합니다.

전역 `KOREAN_INSTRUCTIONS.md`는 PC 온라인·콘솔·모바일 게임을 실제 플레이·배포 가능한 제품의 기준으로 다룹니다. 온라인 여부와 기기 플랫폼을 구분하고 실제 출시 대상은 요청과 프로젝트를 따릅니다. 모든 프로젝트에 모든 플랫폼·온라인 인프라를 추가하거나 브라우저 게임으로 대체하는 지침은 아닙니다. PC 입력/그래픽 옵션/설치형 빌드, 콘솔 SDK/입력/저장/중단·복귀, 모바일 터치/화면/메모리·발열/앱 수명, 온라인 권한/동기화/재접속/데이터 일관성은 해당 대상에만 적용합니다. 이 공통 규칙은 다른 엔진이나 자체 엔진에도 적용됩니다.

2026-10-23 현재 PC의 전역 지침을 기존 파일 일치 확인·백업 후 갱신했습니다. 설치 기록은 `C:\Users\luiny\Strata-data\diagnostics\game-platform-policy-install-20261023.json`입니다. 새 OpenCode/ACP 프로세스부터 반영되며 이번 변경에서 엔진 빌드·온라인 부하·모바일 실기·콘솔 개발기 검증은 수행하지 않았습니다. 필요한 SDK·개발기·서명/인증 환경이 없는 단계는 미완료로 보고하도록 했습니다.

프로젝트 루트에 기존 `AGENTS.md`가 없다면 아래 명령으로 해당 엔진 템플릿을 만듭니다.

~~~powershell
py -3 tools\install_engine_project_guidance.py --engine unreal --project "D:\Games\MyUnrealGame"
py -3 tools\install_engine_project_guidance.py --engine unity --project "D:\Games\MyUnityGame"
~~~

macOS/Linux에서는 `python3 tools/install_engine_project_guidance.py --engine unity --project ~/Games/MyUnityGame`처럼 실행합니다.

도구는 기존 `AGENTS.md`를 절대 덮어쓰지 않습니다. 이미 존재하면 템플릿의 관련 항목을 사람이 검토해 병합합니다. 생성한 `AGENTS.md`는 게임 프로젝트 저장소에 커밋해야 다른 PC와 OpenCode 세션도 같은 규칙을 읽습니다.

각 템플릿에는 다음이 포함됩니다.

- 엔진·프로젝트 버전과 기존 빌드 명령을 먼저 확인하는 규칙
- 모듈·assembly·Blueprint·Scene·Prefab·에셋의 단일 소유권
- 순환 의존성, 병렬 manager·service·state 구현 방지
- 바이너리/직렬화 에셋, 패키지, 엔진 설정의 무단 대량 변경 금지
- 프로젝트가 제공하는 컴파일·Automation Test·Unity Test Framework·포맷·구조 검증만 실행하는 원칙
- 에디터·Cook·Package·Play Mode·대규모 import는 명시 요청 또는 프로젝트 문서가 있을 때만 실행하는 경계
- 아트 방향·대표 플레이 구간·조작감·조명·재질·애니메이션·VFX·HUD의 일관성
- 대상 기기의 프레임 시간/FPS·메모리 예산과 실제 플레이 성능 검증
- UI의 입력 장치·한글·화면 비율·접근성·로딩/오류/복구 상태
- 그래픽 기능·에셋 해상도를 무조건 최대화하지 않고 지원 범위와 측정 근거로 결정하는 원칙

이 작업은 Unreal/Unity를 설치·실행·업그레이드하거나 실제 게임을 빌드·테스트하지 않습니다. 실제 엔진 버전과 각 프로젝트의 정확한 검증 명령은 생성된 `AGENTS.md`에서 채워야 합니다.

## 자동 적용 범위와 품질 한계

공통 품질 기준은 Unity/Unreal 전용이 아닙니다. 전역 한국어 지침은 일반 데스크톱·웹·모바일 앱,
다른 게임 엔진·자체 엔진·엔진 없는 게임에도 적용됩니다. 2D·픽셀 아트에는 스프라이트·레이어·스케일링
등 해당 표현의 기준을 사용하며 3D·실사 그래픽을 강제하지 않습니다. 다른 엔진의 전용 템플릿을
새로 설치하지 않아도 공통 기준은 적용되지만 엔진별 API·렌더 기능 지원은 프로젝트에서 확인해야 합니다.

전역 한국어 지침과 새 클라이언트 setup에는 짧은 UI·게임 품질 기준이 포함됩니다. 엔진별 상세
템플릿은 위 명령으로 해당 프로젝트에 설치해야 하며 기존 AGENTS.md에는 자동 병합하지 않습니다.
이미 설치한 엔진 템플릿도 자동으로 갱신되지 않습니다. 해당 프로젝트를 수정하도록 요청받았을 때
기존 지침을 읽고 필요한 항목만 병합해야 합니다. 이 작업에서는 사용자 게임 프로젝트를 수정하지 않았습니다.

고품질은 지침만으로 보장되지 않습니다. 실제 에셋·아트 작업·엔진 실행·타깃 기기 측정과 시각/플레이
검수가 필요하며, 현재 CUA의 백그라운드 입력 경계도 유지됩니다. UI 유행을 한 스타일로 고정하지 않고
작업할 때 실제 레퍼런스와 해당 플랫폼의 최신 공식 지침을 확인합니다. 작은 코드 수정에서는
관련 없는 UI 재설계나 그래픽 전체 검수를 시작하지 않습니다.

새 제품 구현의 기본 품질 목표는 대형 회사의 출시 제품에서 참고한 일관성·안정성·사용성·완성도입니다.
이를 회사 이름이나 많은 기능으로 판정하지 않고 요청 범위의 레퍼런스·수락 조건·실행 근거로 판단합니다.
게임은 그래픽 외에도 조작·판정·규칙/밸런스·사운드·설정·메뉴/플레이 전환·저장/복구가 해당 범위에
포함되는지 확인합니다. 프로그램·웹은 데이터 보존·권한·응답성·호환성과 필요한 배포·복원 경로를
다룹니다. 프로토타입·짧은 수정의 범위는 유지하며 요청하지 않은 계정·결제·온라인 인프라는 추가하지
않습니다. 지침 검사는 실제 출시 품질·AAA 콘텐츠 제작·성능 검수의 증거가 아닙니다.

2026-10-22 참고한 공식 자료(실제 프로젝트의 버전으로 다시 확인):

- [Unreal 렌더링 성능과 타깃 하드웨어 프로파일링](https://dev.epicgames.com/documentation/en-us/unreal-engine/introduction-to-performance-profiling-and-configuration-in-unreal-engine)
- [Lumen 성능·품질 단계](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-performance-guide-for-unreal-engine)
- [Unity Profiler](https://docs.unity3d.com/Manual/Profiler.html)
- [Unity 렌더 파이프라인](https://docs.unity3d.com/Manual/render-pipelines.html)
- [Apple Motion 지침](https://developer.apple.com/design/human-interface-guidelines/motion)

이번 변경은 템플릿 내용·설치 경로의 오프라인 검사만 수행했으며 실제 그래픽·UI 결과를 검증하지 않았습니다.
