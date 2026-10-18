# Unreal Engine · Unity 프로젝트용 OpenCode 지침

이 저장소의 전역 OpenCode 규칙은 장기 코딩·중복 방지·CUA 경계를 다룹니다. Unreal과 Unity에는 엔진 버전, 에셋 직렬화, 빌드·테스트 명령처럼 프로젝트마다 달라지는 추가 지침이 필요합니다.

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

이 작업은 Unreal/Unity를 설치·실행·업그레이드하거나 실제 게임을 빌드·테스트하지 않습니다. 실제 엔진 버전과 각 프로젝트의 정확한 검증 명령은 생성된 `AGENTS.md`에서 채워야 합니다.
