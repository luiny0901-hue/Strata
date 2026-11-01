param(
    [ValidateSet('install', 'remove', 'configure-keys', 'clear-keys', 'index-sources', 'index-status', 'refresh-index')]
    [string]$Action = 'install',
    [string[]]$SourceId = @(),
    [switch]$AllSources,
    [int]$MaxPagesPerSource = 10,
    [double]$DelaySeconds = 1
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$TemplateDir = Join-Path $RepoRoot 'tools\searxng-local'
$DataDir = Join-Path $env:LOCALAPPDATA 'Strata\SearXNG'
$ComposeFile = Join-Path $DataDir 'compose.yaml'
$SetupHelper = Join-Path $RepoRoot 'tools\configure_claude_searxng.py'
$KeysHelper = Join-Path $RepoRoot 'tools\configure_claude_search_keys.py'
$IndexHelper = Join-Path $RepoRoot 'tools\claude_mcp\local_docs_index.py'

function Get-PythonCommand {
    $candidates = @(
        (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE 'Strata\.venv\Scripts\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw 'Python 3을 찾지 못했습니다. Strata/Claude 설정에 사용하는 Python을 설치하거나 STRATA_CLAUDE_PYTHON을 지정하세요.'
}

function Invoke-DockerCompose([string[]]$ComposeArgs) {
    & docker compose --project-name strata-local-search --file $ComposeFile @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose 실패 (exit $LASTEXITCODE)." }
}

function Invoke-LocalSearchRequest([string]$Uri, [int]$TimeoutSeconds) {
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
    $response = $null
    try {
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Content = $content
        }
    } finally {
        if ($null -ne $response) { $response.Dispose() }
        $client.Dispose()
        $handler.Dispose()
    }
}

function Wait-LocalSearchReady([int]$TimeoutSeconds = 30) {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-LocalSearchRequest 'http://127.0.0.1:8888/config' 3
            if ($response.StatusCode -eq 200) { return $true }
        } catch {
            # The container may still be starting; /config is a local readiness probe.
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-LocalSearchJson {
    $query = [Uri]::EscapeDataString('SearXNG JSON API setup check')
    try {
        $response = Invoke-LocalSearchRequest "http://127.0.0.1:8888/search?q=$query&format=json" 20
    } catch {
        return [pscustomobject]@{ Success = $false; StatusCode = $null; ResultCount = 0 }
    }
    if ($response.StatusCode -ne 200) {
        return [pscustomobject]@{ Success = $false; StatusCode = $response.StatusCode; ResultCount = 0 }
    }
    try {
        $payload = ConvertFrom-Json -InputObject $response.Content -ErrorAction Stop
    } catch {
        return [pscustomobject]@{ Success = $false; StatusCode = 200; ResultCount = 0 }
    }
    if ($null -eq $payload) {
        return [pscustomobject]@{ Success = $false; StatusCode = 200; ResultCount = 0 }
    }
    $resultsProperty = $payload.PSObject.Properties['results']
    if ($null -eq $resultsProperty -or $null -eq $payload.results -or $payload.results -isnot [System.Array]) {
        return [pscustomobject]@{ Success = $false; StatusCode = 200; ResultCount = 0 }
    }
    return [pscustomobject]@{ Success = $true; StatusCode = 200; ResultCount = $payload.results.Count }
}

function Ensure-LocalSearchJson([string]$SettingsFile) {
    if (-not (Wait-LocalSearchReady)) {
        throw 'SearXNG가 30초 안에 준비되지 않았습니다. Docker 컨테이너와 http://127.0.0.1:8888/config 상태를 확인하세요.'
    }

    $check = Test-LocalSearchJson
    if (-not $check.Success -and $check.StatusCode -eq 403) {
        # Recover a stale Windows bind-mounted settings file once, then recheck the JSON route.
        $containerId = (& docker compose --project-name strata-local-search --file $ComposeFile ps -q searxng | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $containerId) {
            throw 'SearXNG JSON 검색이 HTTP 403을 반환했고 컨테이너 ID를 찾지 못해 설정을 복구하지 못했습니다.'
        }
        & docker cp $SettingsFile "${containerId}:/etc/searxng/settings.yml"
        if ($LASTEXITCODE -ne 0) { throw 'SearXNG settings.yml을 실행 컨테이너에 복사하지 못했습니다.' }
        Invoke-DockerCompose @('restart', 'searxng')
        if (-not (Wait-LocalSearchReady)) {
            throw 'SearXNG 설정 동기화 후 서비스가 30초 안에 다시 준비되지 않았습니다.'
        }
        $check = Test-LocalSearchJson
    }

    if (-not $check.Success) {
        if ($check.StatusCode -eq 403) {
            throw 'SearXNG JSON 검색이 설정 동기화와 재시작 후에도 HTTP 403입니다. config/settings.yml의 search.formats에 json을 추가하세요.'
        }
        if ($null -eq $check.StatusCode) {
            throw 'SearXNG JSON 검색 확인 요청이 시간 초과되거나 연결되지 않았습니다. 엔진 응답과 네트워크를 확인하세요.'
        }
        throw "SearXNG JSON 검색 확인이 실패했습니다 (HTTP $($check.StatusCode))."
    }
    Write-Output "SearXNG JSON 검색 확인 완료: HTTP 200, 결과 $($check.ResultCount)개."
}

$python = Get-PythonCommand
if ($Action -eq 'configure-keys') {
    & $python $KeysHelper 'configure'
    if ($LASTEXITCODE -ne 0) { throw 'Claude 검색 키 설정을 완료하지 못했습니다.' }
    Write-Output 'Exa/Tavily 키 설정을 저장했습니다. Claude Desktop을 완전히 종료한 뒤 다시 실행하세요.'
    exit 0
}
if ($Action -eq 'clear-keys') {
    & $python $KeysHelper 'clear'
    if ($LASTEXITCODE -ne 0) { throw 'Claude 검색 키를 지우지 못했습니다.' }
    Write-Output 'Exa/Tavily 키를 Claude agent-tools 설정에서 지웠습니다. 로컬 SearXNG 연결은 유지됩니다.'
    exit 0
}
if ($Action -eq 'index-sources') {
    & $python $IndexHelper 'sources'
    if ($LASTEXITCODE -ne 0) { throw '로컬 문서 출처 목록을 읽지 못했습니다.' }
    exit 0
}
if ($Action -eq 'index-status') {
    & $python $IndexHelper 'status'
    if ($LASTEXITCODE -ne 0) { throw '로컬 문서 색인 상태를 읽지 못했습니다.' }
    exit 0
}
if ($Action -eq 'refresh-index') {
    if ($AllSources -and $SourceId.Count) { throw '-AllSources와 -SourceId를 함께 사용할 수 없습니다.' }
    if (-not $AllSources -and -not $SourceId.Count) {
        throw '갱신할 출처를 -SourceId <id>로 지정하거나 -AllSources를 지정하세요.'
    }
    $indexArgs = @('refresh', '--max-pages', [string]$MaxPagesPerSource, '--delay-seconds', [string]$DelaySeconds)
    if ($AllSources) {
        $indexArgs += '--all'
    } else {
        foreach ($id in $SourceId) { $indexArgs += @('--source', $id) }
    }
    & $python $IndexHelper @indexArgs
    if ($LASTEXITCODE -ne 0) { throw '로컬 공식 문서 색인을 갱신하지 못했습니다.' }
    exit 0
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) {
    throw 'Docker CLI를 찾지 못했습니다. Docker Desktop을 설치하고 실행한 뒤 다시 시작하세요.'
}
$dockerOs = (& docker info --format '{{.OSType}}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop 엔진이 실행 중이 아닙니다. Docker Desktop을 시작한 뒤 다시 실행하세요.' }
if ($dockerOs -ne 'linux') { throw 'Docker Desktop의 Linux 컨테이너 엔진을 켠 뒤 다시 실행하세요.' }

if ($Action -eq 'remove') {
    & $python $SetupHelper 'disable'
    if ($LASTEXITCODE -ne 0) { throw 'Claude MCP 검색 설정을 해제하지 못했습니다.' }
    if (Test-Path -LiteralPath $ComposeFile) { Invoke-DockerCompose @('down') }
    Write-Output "검색 컨테이너를 중지했고 Claude MCP의 로컬 검색 연결을 해제했습니다. 데이터는 $DataDir 에 보존했습니다."
    exit 0
}

$listener = Get-NetTCPConnection -State Listen -LocalPort 8888 -ErrorAction SilentlyContinue
if ($listener) {
    $owned = $false
    if (Test-Path -LiteralPath $ComposeFile) {
        $ids = & docker compose --project-name strata-local-search --file $ComposeFile ps -q searxng 2>$null
        if ($LASTEXITCODE -eq 0 -and $ids) { $owned = $true }
    }
    if (-not $owned) { throw '127.0.0.1:8888이 이미 사용 중입니다. 기존 서비스를 중지하지 않았습니다.' }
}

New-Item -ItemType Directory -Force -Path $DataDir, (Join-Path $DataDir 'cache'), (Join-Path $DataDir 'config') | Out-Null
Copy-Item -LiteralPath (Join-Path $TemplateDir 'compose.yaml') -Destination $ComposeFile -Force
$settingsFile = Join-Path $DataDir 'config\settings.yml'
if (-not (Test-Path -LiteralPath $settingsFile)) {
    $priorSettings = Join-Path $DataDir 'settings.yml'
    if (Test-Path -LiteralPath $priorSettings -PathType Leaf) {
        Move-Item -LiteralPath $priorSettings -Destination $settingsFile
    } elseif (Test-Path -LiteralPath $priorSettings) {
        throw "기존 $priorSettings 경로가 파일이 아니라 디렉터리입니다. 사용자 데이터를 보존하기 위해 자동 변경을 중단했습니다."
    } else {
        Copy-Item -LiteralPath (Join-Path $TemplateDir 'settings.yml') -Destination $settingsFile
    }
}
$envFile = Join-Path $DataDir '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    $rng.Dispose()
    Set-Content -LiteralPath $envFile -Value "SEARXNG_SECRET=$secret" -Encoding ascii -NoNewline
}

Invoke-DockerCompose @('up', '-d', '--pull', 'missing')
Ensure-LocalSearchJson $settingsFile
& $python $SetupHelper 'enable' '--url' 'http://127.0.0.1:8888'
if ($LASTEXITCODE -ne 0) { throw 'Claude MCP 설정이 반영되지 않았습니다. 컨테이너는 중지하지 않았습니다.' }

Write-Output '무료 로컬 SearXNG 검색을 설치하고 Claude agent-tools MCP에 연결했습니다.'
Write-Output '기존 Claude Desktop을 완전히 종료한 뒤 다시 열어 새 MCP 설정을 불러오세요.'
Write-Output '서비스 주소: http://127.0.0.1:8888 (이 PC에서만 접근 가능)'
Write-Output '검색 요청은 선택된 외부 검색엔진으로 전달되며, 외부 엔진의 요청 제한은 적용됩니다.'
