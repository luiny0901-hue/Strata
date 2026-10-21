# REA 재구현 경로 검증 (2026-10-21)

## 실제 실행

이미 캐시에 설치된 rea-agents 6.7.0의 CLI를 직접 실행했다. 패키지·엔진 설치나 대상 앱 실행은 하지 않았다.

- 소유한 시험 대상: 한글·공백 경로의 package.json, Electron main.js, model.js, index.html.
- `analyze-javascript-application <path> --format json`: exit0, Evidence 레코드 반환, 시험 함수 normalizeName 포함 확인.
- 존재하지 않는 대상: exit1, 구조화된 오류 반환.
- 원본 네 파일의 SHA256이 실행 전후 동일.
- 증거: `C:\Users\luiny\Strata-data\diagnostics\rea-reconstruction-20261021-1`의 valid.stdout.json, missing.stdout.json, summary.json 및 stderr.

## 보완

REA 분석 에이전트의 형식별 도구 선택, 타깃 정체성과 근거 연결, 제한된 페이지·소스 선택, 누락 엔진과 부분 결과·timeout 처리, 기능별 구현 인계 규칙을 추가했다. 실제 제공된 스키마만 사용하며 문서에 있다는 이유로 새 도구를 가정하지 않는다. 원본 실행·수정과 분석 엔진 자동 설치는 하지 않는다. 사용자 정의 에이전트는 보존하며 알려진 이전 기본 설정만 갱신한다.

`python -m unittest tools.test_rea_integration`: 11개 통과. 이는 설정 갱신·보존과 지침 전달 검사이며 실제 모델의 모든 판단을 검증한 결과는 아니다.

## 미검증

실제 OpenCode가 REA MCP를 자동 선택하는 과정, UI 렌더링·CUA 상호작용, 새 앱 구현과 원본 비교는 이번 시험에 포함되지 않았다. 임의의 네이티브/.NET/APK/ASAR, 난독화·암호화·서버 의존 앱을 전부 복원했다고 주장하지 않는다. 그러한 판정에는 사용자가 지정한 대상과 기능별 비교가 필요하다.

재현: `python tools/test_rea_reconstruction_runtime.py --cli <캐시의 scripts/rea.mjs> --output <새 진단 폴더>`.
