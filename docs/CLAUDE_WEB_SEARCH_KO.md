# Claude Code 웹 검색 설정

## 모델의 학습 시점과 최신 자료 확인 (2026-11-02 점검)

모델의 출시일이나 학습 기준일만으로 현재 API·지원 상태·최신 논문을 알 수 있다고 가정하지 않습니다. 공통 정본인 `examples/claude/KOREAN_INSTRUCTIONS.md`의 ‘근거·도구’에 최신 자료 확인 기준을 두고 Claude 지침 생성과 Codex 기본 지침 모두에 투사합니다. Claude CLI·Desktop Code는 사용자 `CLAUDE.md`, Codex CLI·ChatGPT Desktop의 Codex 모드는 사용자 `AGENTS.md`를 읽습니다. 일반 ChatGPT 채팅 모드까지 이 지침이 적용된다는 뜻은 아닙니다.

- 최신 정보 답변과 새 설계·기술 선택에서는 공개 자료를 먼저 검색하고 공식 문서·릴리스 노트·논문·공개 저장소 원문을 확인합니다. 날짜·버전·라이선스·유지 상태·호환성과 실제 제품 요구를 비교하며, 최신이라는 이유만으로 업그레이드하지 않습니다.
- 발표·시연·출시·재현된 구현을 구분하고 출처 링크와 확인 한계를 남깁니다. 기본 문법·국소 수정·이미 확인한 같은 버전의 근거에는 불필요한 검색을 반복하지 않습니다. 검색 실패나 0개 결과는 최신 확인 완료가 아닙니다.
- 실제 MCP 검색에서 `include_domains=["python.org"]`인데 다른 사이트 결과가 반환되는 결함을 확인했습니다. 로컬 검색의 `site:` 문구를 엔진이 무시할 수 있어, SearXNG 응답에 도메인·하위 도메인·경로 경계를 다시 검사하도록 수정했습니다. 도메인 위장·경로 접두어 혼동·여러 도메인·무필터 보존 회귀 검사 3개를 추가했습니다.
- 새 소스로 같은 실제 검색을 실행하면 범위 밖 결과가 제거되어 0개였습니다. 공식 페이지 직접 조회는 성공했으나 이 결과로 검색엔진의 최신 정보 수집 품질까지 보장하지 않습니다. 이미 실행 중인 MCP의 메모리 캐시·로드된 모듈은 소스 수정으로 갱신되지 않으므로 검색 필터는 MCP 재연결 또는 새 프로세스에서 반영됩니다.

이번 적용은 기존 설정·개인 지침을 보존한 최소 게시입니다. Claude의 ‘근거·도구’ 앞부분만 바꾸고 Codex의 관리 지침 블록과 그 해시만 갱신했습니다. Codex 전체 동기화는 기존 MCP 블록 보호로 거부되어 설정 파일·MCP·모델·권한은 변경하지 않았습니다. 두 클라이언트 설치 지침에 새 공통 정책이 존재함을 확인했으며 이미 열린 대화의 모델 행동이나 네 GUI의 전체 설계·구현 작업까지 시험한 것은 아닙니다. 지침은 모델의 준수를 돕지만 오래된 모델의 이해·추론 능력이나 모든 최신 자료 발견을 보장하지 않습니다.

## 실제 과제 기반 점검 (2026-11-02)

별도 CLI 대화에서 Strata에 두 과제를 부여했습니다. 정보 과제는 현재 Python·uv 릴리스 및 최근 12개월의 speculative decoding 논문과 공개 구현 조사이고, 구현 과제는 uv·pipx의 공개 근거를 비교한 뒤 표준 라이브러리 기반 GitHub 릴리스 선택 CLI를 작성·검사하는 작업입니다. 프롬프트·실제 도구 이벤트·산출물·종료 영수증은 버전 관리에서 제외된 `.strata-mcp/latest-evidence-20261102/`에 보관합니다. GUI 시험이나 다른 모델의 일반화 시험은 아닙니다.

정보 과제의 최초 실행은 종료 0, 370.33초였습니다. 실제 도구 호출은 `WebSearch` 4회·`WebFetch` 12회였고 MCP 검색은 선택하지 않았습니다. Python 3.15.2·uv 0.13.6, 2026-10-30 제출된 TraceSpec 논문(arXiv 2610.41177)과 Robot2050/TraceSpec 저장소를 조사했습니다. 공식 릴리스 API와 arXiv HTML·저장소 README를 별도로 읽어 버전·논문 존재·날짜·Apache-2.0 코드 라이선스·평가 한계를 대조했습니다. 공개 저장소 코드는 설치하거나 실행하지 않았습니다.

최초 Codex 구현 실행은 종료 1, 102.04초였으며 `Anthropic search history cannot be replayed losslessly` 재연결 오류로 프로그램 파일을 만들지 못했습니다. 설치된 OpenCodex 2.95.0의 모델 카탈로그가 Strata에 `supports_search_tool:true`, `web_search_tool_type:text_and_image`를 광고하는 것도 읽기 전용으로 확인했습니다. 내장 검색 호환성 문제는 지침 보강만으로 해결됐다고 보지 않습니다. 분리 시험에만 `web_search="disabled"`, `features.memories=false`를 전달했고 사용자 전역 설정이나 다른 모델의 검색 설정은 바꾸지 않았습니다.

정보 재시험은 다른 짧은 과제로 실행했으므로 최초 실행과 속도 비교에 쓰지 않습니다. 종료 0, 91.67초이며 `WebFetch` 3회로 공식 페이지를 직접 읽었고 도구 오류는 0건이었습니다. MCP는 연결되어 있었지만 이 과제에서는 호출하지 않았습니다. uv 게시일을 본문 날짜 10월 26일로만 적은 점은 공식 API `published_at=2026-10-27T00:47:49Z`와 구분이 부족해, 릴리스 노트 날짜·원시 게시 시각·시간대 구분을 공통 지침에 추가했습니다.

최초 실행에서 내장 `WebSearch` 우선 선택과 반복적인 529 도구 오류가 관측됐습니다. 공통 정책에 지연 검색으로 MCP `agent-tools.web_search`를 먼저 찾고, 제공되면 우선 사용하도록 명시했습니다. 제한 오류 뒤 같은 경로를 병렬 반복하지 않고 가능한 읽기 전용 공식 HTTP 조회 또는 미확인 보고로 처리하도록 보강했습니다.

검색 경로도 실제 동일 질의로 비교했습니다. `Python latest release site:python.org`를 SearXNG `it` 분류로 보내면 질의응답·코드 사이트가 주로 나왔지만 `general`에서는 공식 다운로드·버전 문서가 나왔습니다. 따라서 외부 API·로컬 공식 색인 경로는 유지하고 SearXNG에 전달하는 개발 검색만 `general`로 변경했습니다. 도메인 응답 필터와 기존 호출 간격은 유지합니다. 수정 후 기존 라우터로 `category=it`, `include_domains=["python.org"]`를 요청해 공식 URL 3개를 확인했습니다. 여러 도메인도 교집합이 아니라 `site:A OR site:B`로 전달하도록 수정했으며 관련 회귀 검사를 추가했습니다.

### 실제 과제의 최종 판정

- **최신 정보·논문 조사:** 공식 페이지·arXiv·공개 저장소 조회를 실제 수행했고 결과를 독립 대조했습니다. 학습 지식만으로 답한 실행은 아니었습니다. 다만 최초 정보 과제에서 MCP 검색은 선택하지 않았으므로 이를 MCP 성공 증거로 사용하지 않습니다.
- **게시 시각 재시험:** `claude-date-after`는 종료 0, 38.40초였고 공식 API를 읽어 uv 0.13.6의 `published_at=2026-10-27T00:47:49Z`를 UTC와 함께 정확히 답했습니다. 릴리스 노트 본문 날짜와 게시 시각의 혼동을 수정한 결과입니다.
- **MCP 기반 설계·구현:** `codex-build-after`는 종료 0, 348.91초였습니다. 실제 `agent-tools.web_search` 호출 3건 중 최초 1건은 잘못된 `max_results` 인자로 실패했고, 모델이 `count`로 고쳐 후속 2건이 완료됐습니다. 공개 문서·GitHub/PyPI 메타데이터를 추가로 읽고 README·release_picker.py·검사를 생성했습니다. 부모 세션에서 모델 작성 검사 20개를 다시 실행하고, 별도로 만든 반례 10개(날짜순 선택·초안 제외·사전 릴리스 선택·시간대·빈 목록·손상 JSON·게시일 오류 등)도 통과했습니다. 시간 수치는 서로 다른 조건·과제이므로 속도 개선율로 비교하지 않습니다.
- **출처 해석 한계:** 생성 README는 uv를 Apache-2.0으로만 적었습니다. 공식 저장소 README는 Apache-2.0 또는 MIT를 선택할 수 있다고 밝히므로 복수 선택 조건이 누락됐습니다. 원래 시험 산출물은 판정 근거로 보존하고 공통 지침에 README·LICENSE 원문과 복수 라이선스 확인을 보강했습니다. 이 라이선스 보강의 추가 모델 행동 시험은 실행하지 않았습니다.
- **기본 내장 검색 경로는 미해결:** 내장 검색 기본값을 끄지 않고 같은 구현 프롬프트를 다시 실행한 `codex-build-native-after`도 종료 1, 65.05초로 같은 검색 이력 호환성 오류가 재현됐습니다. 이 실행은 자동 메모리만 시험 인수로 껐습니다. 내장 검색을 끈 분리 시험의 성공을 기본 경로의 수정 완료로 확대하지 않습니다. 사용자 전역 검색 설정을 바꾸면 다른 모델에도 영향을 줄 수 있어 변경하지 않았고 설치된 OpenCodex 소스도 직접 패치하지 않았습니다.

공통 지침·검색 경로·기존 진단의 관련 검사 149개와 `git diff --check`가 통과했습니다. 현재 설치된 Claude·Codex 공통 지침에는 보강을 게시했으며 모델·권한·서비스는 변경하지 않았습니다. 검색 코드 수정은 새 MCP 프로세스에서 실제 사용됐지만 이미 열린 다른 MCP 인스턴스의 자동 반영은 확인하지 않았습니다. 네 Desktop GUI·다른 모델·다른 OS·모든 작업에서의 준수는 미검증입니다. 시험 산출물과 영수증은 [진단 수락 조건](../.strata-mcp/latest-evidence-20261102/acceptance.json), [정보 조사 답변](../.strata-mcp/latest-evidence-20261102/claude-info/answer.md), [UTC 게시 시각 답변](../.strata-mcp/latest-evidence-20261102/claude-date-after/answer.md), [독립 구현 검사](../.strata-mcp/latest-evidence-20261102/independent-build-tests.json)에서 확인할 수 있습니다. 진단 파일은 로컬에만 있고 버전 관리 대상이 아닙니다.

## 성능·코드 구조 후속 점검 (2026-11-02)

기본 코덱스 지침에는 성능 선택 기준이 직접 포함되지만 코드 소유 경계는 복잡한 작업에서만 별도 문서를 읽도록 되어 있었습니다. `coding_policy()`가 기존 복구 정본의 핵심 네 항목을 추출해 코덱스 기본 지침에 포함하도록 수정했습니다. 응집된 함수·모듈, 명시적인 입출력·오류 경계, 기존 소유 모듈 확장, 중복 구현·순환 의존성 방지 기준을 일반적인 작은 구현에도 전달합니다. 별도 정책 사본을 만들지 않으며 정본 항목이 없어지거나 중복되면 생성을 거부합니다. 클로드의 기존 상세 구조 지침은 유지합니다.

설치된 코덱스의 관리 지침 블록과 해시만 백업 후 갱신했고, 관리 블록 밖의 사용자 지침이 보존됨을 확인했습니다. 모델·MCP·권한·검색 기본값·서비스는 변경하지 않았습니다. 설치 지침 변경은 이미 열린 대화의 재로딩이나 실제 준수를 증명하지 않습니다.

성능 실작업은 별도 임시 폴더에서 상위 K개 이벤트 선택 라이브러리·검사·벤치마크를 만들도록 요청했습니다. 기존 Python 연동·표준 라이브러리 조건에서 N=100000/K=20, N=100/K=20, N=10000/K=8000을 비교하며, 시간·메모리와 정확성을 함께 판단합니다. 시험 수락 조건은 [성능 과제 수락 조건](../.strata-mcp/latest-evidence-20261102/performance-acceptance.json)에 있습니다. 클로드 CLI 실행은 종료 0·233.39초였으며 모델 작성 검사 15개와 독립 검사 72개를 통과했습니다. 독립 측정의 대표 조건 중앙값은 정렬 190.79ms·힙 71.12ms이고, 큰 K에서는 정렬 13.06ms·힙 19.58ms로 오히려 정렬이 빨랐습니다. 이는 Threadripper 3970X·Windows 11·CPython 3.14.7에서 동일 입력·5회 교차 순서로 비교한 해당 두 구현의 결과이며 다른 언어·전체 프로그램의 우위를 증명하지 않습니다. 작은 입력의 중앙값 차이는 약 0.009ms여서 복잡한 경로 분기의 근거로 사용하지 않습니다.

모델의 벤치마크는 시간과 tracemalloc 측정을 분리했지만 객체 재사용 상태를 명시하지 않아 대표 힙 피크를 0.9KB로 보고했습니다. 독립 측정에서 각 측정 전 `gc.collect()`를 수행하고 반환 결과를 유지하면 6,184바이트였고 정렬은 17,600,328바이트였습니다. 입력 생성은 추적 범위 밖이며 이 값은 프로세스 RSS가 아닙니다. 어느 수치도 작업의 절대 메모리 요구량으로 사용하지 않도록 공통 성능 지침에 할당기·객체 재사용 상태와 측정 범위 명시를 보강했습니다. 이 측정 조건 보강은 두 클라이언트의 설치 지침에 백업 후 반영했습니다. 보강 이후의 모델 메모리 보고 행동은 추가 시험하지 않았습니다.

코덱스 성능 과제는 900.02초 제한에 도달해 중단됐습니다. `event_topk.py`와 검사 파일은 만들었지만 `benchmark.py`·README 및 최종 완료 이벤트는 없으므로 구현 과제는 **부분 완료**입니다. 모델 작성 검사 19개와 세 선택 함수에 대한 독립 검사 72개는 부모 세션의 실행에서 통과했습니다. 부모 세션이 별도로 측정한 대표 조건 중앙값은 정렬 119.01ms·힙 37.55ms, 큰 K는 정렬 7.97ms·힙 11.27ms였습니다. 이 측정은 같은 코덱스 산출물 내 두 경로의 비교이며 다른 시각에 실행한 클로드 과제와의 모델·속도 우열 비교에는 사용하지 않습니다. 시간 초과 시 시험 셸만 종료되고 남았던 코덱스 자식 트리는 생성 시각·부모 PID를 대조해 해당 시험 소유 프로세스만 정리했습니다. 다른 클라이언트·OpenCodex·Strata 서비스는 중지하지 않았습니다.

코덱스가 최초 검색에 `max_results`를 보내 거부된 뒤 웹검색을 CUA·REA 하위 도구로 오인해 반복 시도했습니다. 오류 응답이 올바른 인자·호출 경로를 제시하지 않던 부분을 수정해, 지원하지 않는 인자는 계속 거부하되 결과 수는 `count`이고 `web_search`를 직접 호출해야 한다고 안내합니다. 잘못된 하위 경로의 오류도 같은 복구 방법을 제공합니다. 사용자 검색어·인자 값을 오류에 복사하지 않으며, 오류 경로가 CUA·REA 자식을 실행하지 않는 회귀 검사도 추가했습니다. 이 수정은 새 MCP 프로세스에서 반영되며 이미 열린 MCP의 자동 갱신을 보장하지 않습니다.

수정 후 새 MCP를 사용하는 `codex-search-recovery`는 종료 0·28.59초였습니다. 실제 `agent-tools.web_search` 1회로 공식 문서 도메인의 링크를 얻었으며 CUA·REA 호출과 도구 오류는 없고 `turn.completed`를 확인했습니다. 검색 결과와 원문 확인·성능 측정을 구분하는 답변도 저장했습니다. 이 짧은 과제는 오류 복구 안내 수정 후 기본 검색 사용이 가능한지 확인한 것이며, 오류를 강제로 발생시킨 모델 복구 시험이나 전체 성능 구현 재시험은 아닙니다. 오류 응답 자체의 안내·입력 비노출·자식 미실행은 회귀 검사로 확인했습니다.

최종 관련 회귀 검사 97개와 `git diff --check`가 통과했습니다. 최초 검사 명령에서 존재하지 않는 모듈 `tools.test_claude_web_search_router`를 지정해 ImportError 1건이 있었고 실제 검색 검사 파일로 바로잡았습니다. 최종 97개는 현재 수정 소스로 실행한 결과입니다. 원래 코덱스 내장 검색의 이력 호환성 오류는 여전히 미해결이며 시험 인수의 내장 검색 비활성화를 사용자 전역에 적용하지 않았습니다. 챗지피티 데스크톱은 설치 항목은 있으나 실행 중인 창이 없었고, 이번 도구 카탈로그에는 실행 도구가 반환되지 않아 GUI 과제를 실행하지 못했습니다. 클로드 데스크톱도 현재 창 관찰만 했으며 별도 Strata GUI 과제의 완료 증거는 아닙니다.

실행 기록·산출물은 로컬 전용입니다: [클로드 실행 및 도구 감사](../.strata-mcp/latest-evidence-20261102/claude-performance/audit.json), [클로드 독립 검사·측정](../.strata-mcp/latest-evidence-20261102/claude-performance/independent-verification.json), [코덱스 시간 초과 영수증](../.strata-mcp/latest-evidence-20261102/codex-performance/receipt.json), [코덱스 독립 검사·측정](../.strata-mcp/latest-evidence-20261102/codex-performance/independent-verification.json), [코덱스 검색 재시험](../.strata-mcp/latest-evidence-20261102/codex-search-recovery/receipt.json), [설치 지침 반영 영수증](../.strata-mcp/latest-evidence-20261102/memory-policy-apply.json).

## 네 클라이언트의 MCP 검색 우선순위 (2026-11-02 추가 확인)

같은 Windows 사용자·같은 호스트의 저장 설정을 확인했습니다. 클로드 CLI·클로드 데스크톱 Code 로컬 세션은 사용자 `~/.claude/CLAUDE.md`와 `~/.claude.json`의 `agent-tools`를 사용합니다. 코덱스 CLI·챗지피티 데스크톱의 Codex 모드는 사용자 `~/.codex/AGENTS.md`와 `~/.codex/config.toml`의 MCP 구성을 공유합니다. 두 MCP 등록의 실행 파일·인자·환경변수가 같고 SearXNG 주소가 설정되어 있으며, 클로드 전역·프로젝트에 `agent-tools` 비활성화나 별도 재정의가 없고 코덱스에서도 활성 상태였습니다. 이 확인은 일반 ChatGPT 채팅·웹·다른 사용자·원격 호스트의 연결에는 적용하지 않습니다.

공통 정본과 설치된 두 지침에는 이미 MCP 우선 기준이 있었지만 MCP 서버 초기 안내에는 단지 `web_search when available`만 있었습니다. 공통 정본을 더 명확히 하고 서버 초기 안내·도구 설명에도 같은 우선순위를 넣었습니다. 웹검색은 MCP `web_search`를 내장 `WebSearch`·`web.run`·`search_service_web_run`, 브라우저·셸 검색보다 먼저 사용합니다. 지연 도구만 현재 클라이언트의 도구 검색으로 찾고 이미 노출된 도구는 직접 호출합니다. 서버 별칭·접두사는 실제 목록을 따르며 CUA·REA 하위 카탈로그에서 웹검색을 찾지 않습니다. 대체 검색은 MCP 부재·비활성화 또는 실제 호출 실패가 확인된 때로 한정하고 이유를 밝힙니다. 잘못된 인자는 스키마에 맞춰 수정하고 0개 결과를 도구 부재로 판단하지 않습니다. 이미 URL이 정해진 공식 페이지의 원문 읽기는 검색과 구분합니다.

기본 설정의 실제 CLI 시험에서는 두 클라이언트 모두 기록에 나타난 첫 명시적 검색 도구 호출이 MCP였습니다. 모델·내장 검색 비활성화·설정 덮어쓰기 인수를 주지 않았습니다. 그러나 SearXNG가 빈 결과와 검색엔진 요청 제한·CAPTCHA를 함께 반환해 반복 검색이 발생했고, 코덱스는 이후 내장 검색 이력 호환성 오류로 종료 1이었습니다. 클로드는 종료 0이지만 내장 검색 오류와 반복 호출이 있어 전체 성공으로 판단하지 않습니다. 따라서 첫 도구 선택과 검색 과제 성공을 구분합니다.

빈 원본 결과와 유효한 검색엔진 오류가 함께 있으면 이제 명시적인 검색 실패로 반환합니다. 정상적인 빈 결과·도메인 필터로 제거된 결과는 그대로 유지하며, 엔진 일부의 오류만으로 전부 실패했다고 단정하지 않습니다. 실패 안내는 같은 작업에서 검색어만 바꾼 반복을 중단하고 알려진 공식 URL 직접 확인 또는 검색 미완료 보고로 처리하도록 합니다. 코덱스 지침에는 현재 OpenCodex→Strata에서 재현된 내장 검색 이력 오류를 명시해 MCP 실패의 대체로 그 비호환 경로를 선택하지 않도록 했습니다. 다른 공급자·모델의 내장 검색은 변경하지 않습니다. 검색엔진 차단을 해제하거나 CAPTCHA를 우회한 수정은 아닙니다.

서버는 검색 공급자가 설정되어 도구가 노출되는 경우에만 MCP 우선 안내를 보냅니다. 공급자가 없는 경우 사용할 수 없는 검색 도구를 사용하라고 안내하지 않습니다. 관련 회귀 검사는 이 구분과 두 클라이언트의 공통 지침 전달을 확인합니다. 설치 지침은 백업·동시 변경 검사 후 해당 클로드 항목과 코덱스 관리 블록만 갱신했으며 개인 지침·모델·MCP 등록·권한·내장 검색 설정은 보존했습니다. `web_search="disabled"`를 전역에 추가하거나 다른 모델의 검색 기능을 끄지 않았습니다. 우선 사용 지침은 모델의 선택 기준이며 네이티브 도구를 차단하는 강제 실행 정책은 아닙니다.

최종 관련 검사 103개와 `git diff --check`가 통과했습니다. 새 세션의 실패 처리 재시험에서도 모델·설정·내장 검색 비활성화 인수를 주지 않았고, 두 CLI 모두 첫 검색으로 MCP를 선택했습니다. 클로드는 종료 0·49.01초였으나 MCP 2회 후 내장 검색 2회도 시도해 반복·대체 경로 제한의 완전한 준수는 입증하지 못했습니다. 코덱스는 종료 0·102.93초·`turn.completed`였으며 MCP 1회가 검색엔진 오류로 실패한 뒤 추가 검색 없이 실패·확인 한계만 기록했습니다. 어느 쪽도 실제 검색 결과 링크를 얻지 못했으므로 **MCP 우선 선택·실패 보고 검증**이지 검색 공급자의 복구·검색 성공이 아닙니다. 두 과제는 실패 시 종료 조건도 명시한 짧은 후속 시험으로 이전 과제와 속도를 비교하지 않습니다. 데스크톱 두 앱은 같은 호스트의 공통 설정 전달까지 확인했으며 별도 새 GUI 대화의 행동은 미검증입니다.

로컬 근거: [저장 설정·우선 지침 확인](../.strata-mcp/latest-evidence-20261102/priority-delivery.json), [지침 반영 영수증](../.strata-mcp/latest-evidence-20261102/search-priority-apply.json), [기본 실행·후속 실행 감사](../.strata-mcp/latest-evidence-20261102/priority-audits.json), [클로드 실패 보고](../.strata-mcp/latest-evidence-20261102/claude-priority-after/answer.md), [코덱스 실패 보고](../.strata-mcp/latest-evidence-20261102/codex-priority-after/answer.md). 이전 실패 기록은 삭제하지 않았습니다.

공식 문서의 적용 범위는 [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp), [Codex 설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference)를 확인했습니다. 사용자 범위 MCP의 공유와 검색 도구 우선순위 강제는 다른 개념입니다. MCP 서버 코드·초기 안내 변경은 새 MCP 연결에서 읽히며 이미 열린 데스크톱 세션의 메모리·캐시 자동 갱신은 확인하지 않았습니다.

## 남은 검색 문제의 실제 수정·재시작 체크포인트 (2026-11-02)

요청 범위는 검색 가용성·반복 호출·코덱스 이력 호환성·두 데스크톱 실제 동작입니다. 기존 변경과 모델·권한·다른 공급자 설정을 보존하며 커밋·푸시는 하지 않습니다.

- 검색 가용성: 설치된 SearXNG의 기본 웹 엔진들이 제한 상태였습니다. Bing 단독 시험은 무관한 결과를 반환해 채택하지 않았고, 관련 공식 문서를 반환한 독립 오픈소스 Mwmbl 엔진을 기존 기본 설정에 추가했습니다. 설정은 백업 후 기존 검색 컨테이너만 한 번 재시작했습니다. 이후 기존 MCP 라우터의 실제 검색에서 `docs.python.org/3/library/heapq.html` 등 공식 문서 3건을 확인했습니다. 일부 기존 엔진의 CAPTCHA·제한은 여전히 있을 수 있으며 무제한 가용성을 보장하지 않습니다.
- 반복 호출: `SearXNGSearchError.cooldown_seconds`를 기존 `UsageLedger.provider_cooldowns`에 연결했습니다. 장애 응답 뒤 30~60초 동안 검색어·클라이언트가 달라도 외부 요청을 보내지 않습니다. 간격 대기 중인 요청도 동일한 원자적 장부 확인을 거칩니다. 정상 검색·결과 캐시는 유지하며 새 서비스·별도 상태 저장소는 만들지 않았습니다. 관련 검사 106개와 패치 설치 안전성 5개가 통과했습니다.
- 데스크톱 실제 확인: CUA의 일반 텍스트 입력은 백그라운드 미지원이었고 전경 승인도 현재 연결에서 제공되지 않았습니다. 별도로 제공된 CUA `set_value`의 접근성 값 설정은 두 앱 모두에서 실제 값 읽기로 확인됐고, 백그라운드 보내기 버튼으로 시험을 제출했습니다. 클로드 데스크톱 Code의 [검색 연결 검증](#local_f7ff6e4d-b0c1-41a3-bed6-c190d31a3302)과 챗지피티 데스크톱 Codex의 ‘Python heapq 문서 검색’에서 공식 문서 링크·MCP 도구 이름과 완료 답변을 확인했습니다. 사용자 전역 입력·셸 입력 우회는 사용하지 않았습니다.
- 코덱스 이력 오류 원인: Strata `serve/server.py`가 실제 추론 블록에 `signature:""`를 명시하는 반면 OpenCodex 2.95.0 `src/adapters/anthropic-replay.ts`가 문자열 길이 0을 거부했습니다. 공식 v2.95.0 태그 `9df4f6a56483ffe62526e29c7d9c6eeed3e742f4`의 별도 소스에서 실패를 재현하고 빈 문자열을 그대로 보존하도록 한 조건만 수정했습니다. 누락·null·숫자 서명은 계속 거부하고 임의 서명 생성·추론 삭제·도구 ID 변경은 하지 않습니다. 원본 서명과 위조 스냅샷 거부·취소·메모리 경계를 포함한 Bun 검사 126개, 공식 Bun 타입 검사 2,253개 파일, 구조·개인정보 검사와 문서 빌드가 통과했습니다. 초기 `bun run` 경로는 설치 스크립트를 끈 Bun 실행기 연결 문제로 실패하여 등록된 Bun으로 동일 검사 진입점을 직접 실행했습니다. 전체 OpenCodex 검사는 실행하지 않았습니다.
- 설치·반영: 검증된 한 줄 소스 변경을 `tools/patch_opencodex_search_replay.py`로 2.95.0 설치에만 백업·동시 변경 확인 후 반영했습니다. 다른 버전·알 수 없는 소스 구조는 거부하며 재적용은 무변경입니다. 이는 이 PC의 유지보수 패치이며 공식 OpenCodex 배포에 포함된 수정이 아닙니다. npm 업데이트 후에는 버전과 소스를 다시 검증해야 합니다. 현재 서비스 PID는 9400으로, 런타임 반영을 위한 기존 소유자의 안전한 재시작과 반영 후 실제 native-search·MCP 왕복이 아직 남았습니다.

재시작 반영은 세 단계 끝에 완료했습니다. ① `ocx service restart`는 종료 코드 0을 반환했지만 PID 9400과 제공 시각이 그대로였고, 예약 작업만 다시 실행돼 도중에 자식을 살리는 래퍼와 기존 프록시가 남았습니다. ② 재시작 경로에 기존 설치 정리(`prepareServiceInstall`)를 연결한 수정을 클론 소스와 검증된 2.95.0 설치에 백업 후 반영해 재실행하자, 이번에는 프록시가 “재실행 가능한 Task Scheduler 래퍼 아래에서는 `ocx stop`으로만 정지할 수 있다”며 아무것도 바꾸지 않고 거부했습니다. ③ 그 규칙대로 `ocx stop`(래퍼 종료·추적 프록시 정지·재실행 창 검증) → 포트 다운 확인 → `ocx service start`을 실행해 PID가 9400에서 34532로 바뀌고 제공 시각이 2026-11-02T13:47:32Z로 갱신된 것을 영수증과 healthz로 확인했습니다. 각 시도 영수증은 `search-restart-receipt-attempt1~3.json`과 최종 `search-restart-receipt.json`, 실패 로그는 `search-restart-output.txt`에 있습니다. 이 설치 정리 변경은 로컬 유지보수 패치이며(마커 `STRATA_OPENCODEX_SEARCH_REPLAY_V2`), npm 업데이트 후에는 버전·소스를 다시 검증해야 합니다.

사용자 지침에 따라 검증 기준을 **ChatGPT·Codex 구독 없는 상태**로 바꿨습니다(구독 해지 예정). 기준을 설정으로도 확정했습니다. `~/.codex/config.toml`에 `web_search = "disabled"`를 백업 후 추가(`subscription-free-baseline.json`)해, 코덱스 CLI·챗지피티 데스크톱이 같은 호스트 설정에서 요금제 의존 hosted 검색 도구를 요청에 싣지 않습니다. 지침도 “버그라 피한다”에서 “구독 없음이 전제라 기본·대체 경로가 아니다”로 바꿔 클로드 섹션과 코덱스 관리 블록에 백업 후 재적용했고, 관련 검사 55개가 통과했습니다. 주의: 이 설정 항목은 서비스 정지·시작 복원 절차에서 기본 모델 항목과 함께 사라질 수 있으므로, 재시작 후에는 `model`·`web_search`·`openai_base_url` 세 항목을 함께 확인하고 필요 시 `restore_codex_model.py`와 `apply_subscription_free_baseline.py`로 복원합니다.

기준 설정 후 코덱스 검색 왕복을 재확인했습니다(`codex-baseline-verify2/`, 종료 코드 0·`turn.completed`·322.14초). hosted 도구 없이 MCP `web_search` 호출 한 번(첫 시도는 `domain` 오인자가 새 오류 안내로 즉시 `include_domains`·`count`로 복구)으로 공식 heapq 링크를 얻고, 허용된 공식 HTTP 조회로 성능 권고 원문을 검증해 answer.md에 저장했습니다. 답변 저장 셸 호출 2회는 따옴표 문제로 실패 후 같은 턴에서 재시도 성공입니다. 직전 시도들의 지연은 검색엔진 일시 제한(`codex-native-replay-verify-blocked/`)과 대기(`codex-baseline-verify-slow1/`) 때문이었고 설정 결함은 아니었습니다. 기준 변경으로 드러난 사실:

- 이전 재현 시험의 “You’ve hit your usage limit”은 Strata 경로의 문제가 아니었습니다. `ocx stop → ocx service start` 과정에서 `~/.codex/config.toml`의 최상위 `model` 항목이 사라져(저널의 originalConfig 스냅샷에 이 항목이 없었음) 이후 요청이 OpenAI 통과 모드로 바뀌면서 요금제 한도에 걸렸습니다. 2026-11-02 19:58 감사에서 확인한 값(`strata/qwen3.8-flash-next-unsloth-ud-iq4_xs`)을 백업 후 정확히 복원했고(`codex-model-restore.json`), 복원 후 검색 없는 일반 코덱스 왕복이 종료 코드 0·Strata 응답으로 완료됐습니다. 요금제 잔여량 없이 동작하는 경로입니다.
- 후속 주의: 이 소실은 서비스 정지·시작 주기에서 재발할 수 있습니다. 재시작 후에는 `tools/strata_client_settings.py --codex-only --check`의 `codex_saved_model`이 `null`이 아닌지 확인하고, 사라졌으면 같은 복원 스크립트로 되돌립니다.
- 구독 해지 후 한 번 더 확인할 항목: ① 무료 계정으로 챗지피티 데스크톱 Codex 모드와 코덱스 CLI 로그인·실행이 유지되는지, ② 코덱스 요청에서 hosted 검색 도구가 계속 비노출인지(`web_search = "disabled"` 설정 유지), 해지 후에도 사용량 제한성 신규 오류가 나오지 않는지 확인합니다. 설정이 복원 주기로 사라졌다면 위 복원 절차를 따릅니다. 유료 hosted 검색을 되살리고 싶을 때만 사이드카 백엔드(Google Antigravity `gemini` 같은 구독 독립 대체 포함) 재구성·유효화 결정을 새로 내립니다. ③ MCP `web_search`(Exa→Tavily→SearXNG)와 SearXNG 경로는 구독과 무관하게 계속 동작합니다(오늘 반복 확인).
- 빈 서명 수정의 끝-간 재현은 모델 복원 후 다시 시도했습니다. 내장 검색 지시 과제(`codex-native-replay-verify/`)는 300초 안에서 원래 502 오류 없이 종료됐지만, 정작 그 실행의 도구 목록에는 합성 hosted `web_search`가 노출되지 않고 MCP·연결 검색 항목만 확인됐습니다(코덱스 코드 모드에서 내장 검색 제공 여부가 구독·계정 상태에 좌우되는 것으로 보입니다). 그래서 이 시도로는 오류 제거를 확정하지 않고, 수정 자체의 근거는 루프 검사 126개로 두며 끝-간 확정은 아래 ②번(해지 후, hosted 도구가 노출될 때 명시적 이름 지정)으로 옮깁니다. 원래 실패 재현 영수증은 `codex-native-replay-verify-blocked/`에 보존했습니다. 재개 시에는 위 영수증 상태를 먼저 확인하고 재시작을 중복 제출하지 않습니다. 실제 GUI 검증 결과는 이미 확보했으며 재시작만으로 무효화하지 않습니다. 커밋·푸시는 하지 않았습니다.

## 검색 순서

Claude Code의 `agent-tools` MCP가 `web_search` 하나를 제공하며 검색 때 다음 순서로 자동 처리합니다.

1. 최근 동일 검색은 프로세스 메모리 캐시를 확인합니다. 보통 10분, 뉴스·기간 지정 검색은 2분 동안 재사용하며 동시에 같은 검색이 들어오면 한 번만 공급자에 보냅니다. 문서 색인을 갱신하면 캐시 키도 바뀌어 갱신 전 결과를 재사용하지 않습니다.
2. 자주 쓰는 공식 개발 문서의 로컬 색인을 확인합니다. 명시한 지원 도메인 검색은 색인 결과가 있으면 사용하고, `category=it` 일반 검색은 결과가 충분할 때만 로컬 결과를 사용합니다. 시간 범위/최신성 필터가 있으면 로컬 스냅샷을 건너뜁니다.
3. 캐시나 적합한 로컬 문서 결과가 없으면 **Exa 무료 검색**을 사용합니다. 기본은 `auto`이며 저지연·저비용 검색은 `mode=lite`로 지정할 수 있습니다.
4. Exa 월간 한도·요청 제한에 걸리면 **Tavily 무료 검색**으로 한 번 전환합니다. `basic` 검색은 1 API credit입니다.
5. 두 API를 사용할 수 없으면 **이 PC의 SearXNG**로 넘깁니다. 검색어는 선택된 외부 검색엔진으로 전달됩니다.

검색은 외부 API와 엔진에 나가는 비용이 들 수 있으므로, 캐시가 없는 요청을 자동 재시도하거나 여러 공급자에 병렬로 보내지 않습니다. 명확한 한도·인증·429 응답에서만 다음 공급자로 넘어갑니다. 연결 시간 초과나 모호한 5xx 응답은 이미 처리됐을 가능성을 고려해 자동 중복 호출을 하지 않습니다.

## 무료 사용 한도와 결제 방지

- Exa Starter는 현재 월 `$10` 검색 크레딧을 제공하며 결제수단 등록이 필요하지 않습니다. 검색 가격은 최대 10개 결과 기준 Lite가 1,000회당 `$4`, Auto가 1,000회당 `$7`이고, 페이지 하이라이트/내용에는 별도 페이지 단가가 있습니다. 로컬 라우터는 검색당 2센트를 미리 예약하고 월 `$8` 상당인 400회에서 Exa 호출을 멈춰 여유를 둡니다. [Exa 요금](https://exa.ai/pricing)
- Tavily Free는 현재 월 1,000 API credit이며, `basic` 검색은 1회당 1 credit입니다. 로컬 라우터는 900회에서 Tavily 호출을 멈춰 100 credit을 남깁니다. 무료 크레딧은 매월 1일에 초기화된다고 안내합니다. [Tavily 요금](https://www.tavily.com/pricing), [Tavily Search API 사용량](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- 사용량 장부는 `%LOCALAPPDATA%\Strata\WebSearch\usage.sqlite3`에 검색어를 저장하지 않고 회수와 시각만 보관합니다. Windows 재부팅과 Claude 재시작 뒤에도 월별 안전 한도가 유지됩니다.
- 반복 검색 캐시는 프로세스 메모리에만 보관하며 디스크에 검색어·결과를 저장하지 않습니다. Claude를 완전히 종료하면 캐시는 지워집니다. 정규화된 검색 조건이 같을 때만 재사용합니다.
- 로컬 문서 색인은 `%LOCALAPPDATA%\Strata\WebSearch\docs.sqlite3`에 선택한 공식 문서 본문을 저장합니다. 검색어는 색인에 저장하지 않습니다. 색인은 아래 허용 목록의 HTTPS 도메인/경로만 받으며 robots.txt를 확인하고, 페이지당 1초 이상 간격으로 갱신합니다.
- **결제되지 않게 하려면 두 서비스 모두 무료 계정·무료 키만 사용하고 결제수단을 등록하거나 유료 Pay-as-you-go 플랜을 켜지 마세요.** 이 라우터의 로컬 상한은 보호 장치이지 계정 청구 설정을 대신하지 않습니다. 같은 키를 다른 앱이나 기기에서 같이 쓰면 그 사용량은 로컬 장부에 반영되지 않습니다.

무료 API 한도가 끝난 뒤에도 SearXNG를 통해 비용 없이 검색을 시도할 수 있지만, 이를 무제한이나 IP 차단이 없는 검색이라고 보장할 수는 없습니다. SearXNG는 요청을 공개 검색엔진에 전달하므로 해당 엔진의 CAPTCHA, 429, IP 차단과 가용성 제한을 그대로 받습니다. 로컬 라우터에는 시간당·일일 검색 횟수 상한을 두지 않고, Claude 세션 사이에도 SearXNG 요청 간 최소 5초 간격을 적용합니다. 5초보다 빨리 들어온 요청은 취소 신호를 확인하며 간격이 될 때까지 기다립니다. SearXNG가 CAPTCHA나 429를 감지한 원본 엔진은 자체 중지 시간 동안 검색 대상에서 빠질 수 있습니다. [SearXNG Search API](https://github.com/searxng/searxng/blob/master/docs/dev/search_api.rst)

공개 검색엔진 정책을 우회하는 프록시 회전, CAPTCHA 우회, 자동 반복 호출은 사용하지 않습니다. 그러므로 “무료·무제한·IP 차단 없음”을 한꺼번에 만족시키는 기술적 방법은 없습니다. 실제 동작은 무료 API 잔여량과 각 공개 검색엔진의 정책에 따릅니다.

## API 키 설정

이 설정을 읽은 시점에는 현재 사용자 프로세스에 `EXA_API_KEY`와 `TAVILY_API_KEY`가 없었습니다. 따라서 코드가 바뀌어도 키를 등록하기 전까지는 설정된 로컬 SearXNG만 사용할 수 있습니다.

1. [Exa](https://dashboard.exa.ai/)와 [Tavily](https://app.tavily.com/)에서 각각 무료 계정을 만들고 API 키를 발급합니다. 두 계정에서 무료 플랜을 유지하고 결제수단을 등록하지 않습니다.
2. 저장소의 `setup-free-web-search.bat configure-keys`를 실행합니다. 키 입력은 화면에 표시되지 않습니다. 빈 입력은 기존 값을 유지합니다.
3. 이 명령은 키를 `%USERPROFILE%\.claude.json`의 `mcpServers.agent-tools.env`에만 저장합니다. 이 파일은 사용자 PC에 있는 일반 설정 파일이며 키가 암호화되지는 않으므로 공유하거나 저장소에 올리지 마세요.
4. Claude Desktop을 알림 영역에서도 완전히 종료한 뒤 다시 열고 새 Code 대화를 시작합니다. 새 MCP 프로세스가 키를 읽습니다.

API 키만 지우고 로컬 SearXNG는 유지하려면 `setup-free-web-search.bat clear-keys`를 실행합니다. 전체 로컬 검색 서비스를 중지하고 Claude MCP에서 SearXNG 주소를 해제하려면 `setup-free-web-search.bat remove`를 실행합니다. 사용량 장부와 공식 문서 색인은 남습니다.

## 공식 문서 로컬 색인

기본 허용 목록은 Unity Manual, Unreal Engine 문서, Hugging Face 문서, GitHub 문서, Python 문서, Claude Platform 문서, Claude Code 문서입니다. 출처 ID와 현재 색인 상태를 확인합니다.

```powershell
setup-free-web-search.bat index-sources
setup-free-web-search.bat index-status
```

처음에는 필요한 출처만 갱신하세요. 기본은 출처당 최대 10페이지이며, 최대 100페이지까지 지정할 수 있습니다. 페이지와 사이트맵 요청 사이에는 최소 1초를 둡니다. robots.txt를 읽을 수 없으면 해당 출처 갱신을 건너뜁니다. 사이트맵이 없거나 부족하면 허용된 시작 페이지에서 같은 사이트의 문서 경로 링크를 따라갑니다. robots 정책에서 허용하지 않는 페이지는 저장하지 않습니다. 갱신은 읽어 온 URL만 교체하고 나머지 기존 문서는 보존합니다. 출처별 저장 상한은 300페이지이며 초과하면 오래된 스냅샷부터 정리합니다.

```powershell
setup-free-web-search.bat refresh-index -SourceId unity-manual -MaxPagesPerSource 20
setup-free-web-search.bat refresh-index -SourceId unreal-engine -SourceId huggingface-docs
```

모든 출처를 한 번에 갱신할 수도 있습니다. 기본 10페이지씩 최대 60페이지를 받으므로 네트워크와 사이트 정책을 고려해 필요한 경우에만 실행하세요.

```powershell
setup-free-web-search.bat refresh-index -AllSources
```

갱신한 자료는 검색 결과에 `indexedAtUtc`로 표시됩니다. 버전 확인, 최근 변경, 뉴스, 최신성 필터 검색은 오래된 로컬 스냅샷을 사용하지 않고 Exa/Tavily/SearXNG 경로로 갑니다. 로컬 색인은 외부 웹 전체나 GitHub 코드 저장소를 복제하지 않습니다.

## 일상 검색과 개발 검색

일상 검색도 Claude Code의 `web_search`로 요청하면 됩니다. 기본은 Exa Auto 한 번이며, Exa가 무료 한도에 도달하면 Tavily Basic으로 넘어갑니다. 비용을 아끼려면 `mode=lite`를 지정하세요. 둘 다 소진된 뒤에는 로컬 검색의 속도 제한 안에서 SearXNG를 사용합니다.

전문 개발 정보는 검색 범위를 좁혀 호출 수와 불필요한 결과를 줄이세요.

- 게임엔진 최신 API: `category=it`, `include_domains=["docs.unity3d.com"]` 또는 `include_domains=["dev.epicgames.com"]`
- 오픈소스 구현 사례: `include_domains=["github.com"]`
- 모델·가중치·데이터셋: `include_domains=["huggingface.co"]`
- 논문: `category=science` 또는 `category=publication`
- 최신 소식: `category=news`, `time_range=day` 또는 `month`
- 일반 일상 검색: `category=general`, `language=ko`

Exa 검색어는 Exa로, fallback 시 Tavily 검색어는 Tavily로, 마지막 단계에서는 SearXNG를 통해 외부 엔진으로 전송됩니다. 비공개 코드, 저장소 이름, 로그, 자격증명, 개인 정보는 검색어에 넣지 않습니다. 검색 결과는 출처 발견용으로만 보고, 버전/API/라이선스/보안 정보는 원문과 공식 문서에서 확인합니다.

## 로컬 서비스 정보

- 설치 명령: `setup-free-web-search.bat install`
- 주소: `http://127.0.0.1:8888` — 이 PC에서만 접근
- 컨테이너: Docker Compose `unless-stopped`
- 설정: `%LOCALAPPDATA%\Strata\SearXNG\config\settings.yml`
- 설치는 SearXNG 준비 상태와 JSON 검색을 확인한 뒤 Claude 연결을 저장합니다. JSON 검색이 HTTP 403이면 호스트 설정을 컨테이너에 한 번 다시 적용하고 재시작해 재확인합니다. 설치 확인 검색어는 외부 검색엔진으로 전달됩니다.
- 사용량 장부: `%LOCALAPPDATA%\Strata\WebSearch\usage.sqlite3`
- 공식 문서 색인: `%LOCALAPPDATA%\Strata\WebSearch\docs.sqlite3`
- 반복 검색 캐시: Claude `agent-tools` MCP 프로세스 메모리(디스크에 보존하지 않음)
- 구현: `tools/claude_mcp/web_search_router.py`, `exa_search.py`, `tavily_search.py`, `searxng_search.py`, `usage_ledger.py`
- 로컬 색인 구현/출처: `tools/claude_mcp/local_docs_index.py`, `local_docs_sources.json`; 캐시 구현: `search_cache.py`

SearXNG Search API는 질의를 외부 검색 서비스로 전달합니다. JSON API가 필요하므로 `settings.yml`에서 `search.formats`에 `json`을 유지해야 합니다. [공식 API 설명](https://github.com/searxng/searxng/blob/master/docs/dev/search_api.rst)
