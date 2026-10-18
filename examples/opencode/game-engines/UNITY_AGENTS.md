# Unity 프로젝트 지침

## 시작 전 확인

- `ProjectSettings/ProjectVersion.txt`, `Packages/manifest.json`, `Packages/packages-lock.json`, 기존 CI·테스트·빌드 명령을 먼저 확인한다. Unity 버전·패키지·렌더 파이프라인·플랫폼 설정을 추측으로 변경하지 않는다.
- 기존 `Assets/` 코드, Assembly Definition (`.asmdef`), 테스트, ScriptableObject, MonoBehaviour, 서비스·시스템·매니저를 먼저 찾는다. 같은 역할의 두 번째 manager/store/service 또는 병렬 상태 모델을 만들지 않는다.

## 구조와 구현

- 기능은 가장 가까운 기존 assembly와 공개 API 하나가 소유한다. runtime/editor/test assembly 의존성은 한 방향으로 유지하고 순환 참조를 만들지 않는다. Editor 전용 코드는 runtime assembly에 넣지 않는다.
- ScriptableObject는 데이터와 설정의 소유 경계를 명확히 하고, 게임 상태·규칙을 Scene, Prefab, MonoBehaviour, static singleton에 중복 저장하지 않는다.
- Scene·Prefab·`.asset` YAML은 사용자가 지정한 좁은 변경만 한다. 정확한 직렬화 의미를 확인하지 못하면 직접 병합·대량 치환·GUID 수정·에셋 이동을 하지 않는다. 에디터 GUI가 필요한 조작은 대상과 결과를 화면에서 확인한다.
- `ProjectSettings/`와 `Packages/` 변경은 관련 파일·패키지의 기존 소유 범위 안에서만 한다. 자동 업그레이드·재임포트·Library 삭제는 요청 없이는 하지 않는다.

## 검증과 보고

- 프로젝트가 제공하는 Unity Test Framework, Batch Mode, 컴파일·포맷·정적 분석 명령만 사용한다. 에디터, Play Mode, 대규모 import, 플랫폼 빌드·패키징은 요청 또는 문서화된 검증 절차 없이는 시작하지 않는다.
- 변경 후에는 관련 Edit Mode/Play Mode 테스트, C# 컴파일, asmdef 영향과 에셋 참조 검증을 실행한 사실과 결과를 기록한다. 실행할 수 없는 엔진·플랫폼 검증은 `NOT_RUN`으로 남긴다.
- 완료 보고에는 기존 기능 소유자, 수정한 assembly·Scene·Prefab·에셋, 새 의존성, 실행한 검증, 미실행 검증, 남은 위험을 적는다.
