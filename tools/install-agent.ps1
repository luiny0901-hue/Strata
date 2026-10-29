$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$installerArguments = @($args)
$strataRoot = Split-Path -Parent $PSScriptRoot

function Find-StrataPython {
    if ($env:STRATA_CLAUDE_PYTHON) {
        $candidate = $env:STRATA_CLAUDE_PYTHON
        $resolved = & $candidate -c 'import sys; assert sys.version_info >= (3,10); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $resolved) { throw 'STRATA_CLAUDE_PYTHON 실행 파일을 확인하세요. 다른 경로로 대체하지 않습니다.' }
        return ($resolved | Select-Object -Last 1).Trim()
    }
    foreach ($candidate in @((Join-Path $strataRoot '.venv\Scripts\python.exe'),
            (Join-Path $env:USERPROFILE 'Strata\.venv\Scripts\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'), 'python', 'python3', 'py')) {
        if (-not (Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue)) { continue }
        $pythonArguments = @('-c', 'import sys; assert sys.version_info >= (3,10); print(sys.executable)')
        if ($candidate -eq 'py') { $pythonArguments = @('-3') + $pythonArguments }
        try {
            $resolved = & $candidate @pythonArguments 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) { return ($resolved | Select-Object -Last 1).Trim() }
        } catch { continue }
    }
    return $null
}

try {
    $python = Find-StrataPython
    if (-not $python) {
        if ($installerArguments -contains '--plan') {
            Write-Host '계획: Python 3.12를 준비한 뒤 OS별 통합 설치 계획을 표시합니다. 변경 없음.'
            exit 0
        }
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Windows 앱 설치 관리자(winget)가 필요합니다: https://aka.ms/getwinget . 설치 후 같은 파일을 다시 실행하세요.'
        }
        Write-Host 'Python을 설치합니다. OS 확인창이 나타나면 직접 확인하세요.'
        & winget install --exact --id Python.Python.3.12 --scope user --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity --silent
        if ($LASTEXITCODE -ne 0) { throw 'Python 설치가 완료되지 않았습니다. 재부팅이 필요하면 재부팅 후 다시 실행하세요.' }
        $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $python = Find-StrataPython
        if (-not $python) { throw 'Python 실행 파일을 확인하지 못했습니다. 새 터미널에서 다시 실행하세요.' }
    }
    & $python -B -X utf8 (Join-Path $strataRoot 'tools\install_strata_agent.py') @installerArguments
    exit $LASTEXITCODE
} catch {
    Write-Host ('설치 대기: ' + $_.Exception.Message) -ForegroundColor Yellow
    exit 2
}
