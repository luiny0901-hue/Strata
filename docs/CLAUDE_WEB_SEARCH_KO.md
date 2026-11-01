# Claude Code 웹 검색 설정

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
