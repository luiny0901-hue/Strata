param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ClientArgs)
$ErrorActionPreference = 'Stop'
if (-not $ClientArgs) {
    while ($true) {
        Clear-Host
        Write-Host 'Strata 코딩 도우미' -ForegroundColor Cyan
        Write-Host ''
        Write-Host '1. 처음 설정 / 연결 주소 변경 (필요한 프로그램도 설치)'
        Write-Host '2. 사용 시작 (설정을 마친 뒤 선택)'
        Write-Host '3. 연결 문제 확인'
        Write-Host '4. 이 Windows PC의 모델 서버 켜기'
        Write-Host '5. 현재 작업 설정 내보내기 (다른 PC / 초기화 대비)'
        Write-Host '0. 종료'
        Write-Host ''
        Write-Host '다른 PC의 서버를 사용한다면 1번부터 시작하세요.'
        $choice = Read-Host '번호를 입력하고 Enter'
        if ($choice -eq '0') { exit 0 }
        if ($choice -eq '4') {
            Write-Host '서버 엔진과 모델을 복원한 PC에서만 사용할 수 있습니다.'
            $mode = Read-Host '무검열 모드: 1=ON, 2=OFF, 나머지=취소'
            if ($mode -in @('1','2')) {
                $suffix = 'off'; if ($mode -eq '1') { $suffix = 'on' }
                $repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
                $bat = Join-Path $repo "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-$suffix.bat"
                Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c ""' + $bat + '""') -WorkingDirectory $repo
                Write-Host '서버 창을 열었습니다. 오류 없이 준비된 뒤 이 메뉴의 1번 또는 2번을 사용하세요.'
            }
        } else {
            $action = switch ($choice) { '1' { 'setup' } '2' { 'run' } '3' { 'doctor' } '5' { 'export-profile' } default { $null } }
            if (-not $action) { continue }
            $hostExe = (Get-Process -Id $PID).Path
            & $hostExe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath $action
            if ($LASTEXITCODE -ne 0) {
                Write-Host '완료되지 않았습니다. 위 오류를 확인하세요. 같은 메뉴를 다시 선택할 수 있습니다.' -ForegroundColor Yellow
            } elseif ($action -eq 'setup') {
                Write-Host '설정을 마쳤습니다. 2번으로 시작하거나 Rider를 다시 열고 OpenCode Strata를 선택하세요.'
            }
        }
        [void](Read-Host 'Enter를 누르면 메뉴로 돌아갑니다')
    }
}
function Refresh-Path {
    $env:PATH = $env:PATH + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') + ';' + "$env:APPDATA\npm"
}
function Install-PackageId([string]$Id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Windows App Installer (winget) is required. Install App Installer from Microsoft Store, then rerun setup.'
    }
    Write-Host "Installing missing prerequisite: $Id"
    & winget install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Installation failed: $Id (exit $LASTEXITCODE). Rerun setup after resolving the installer error." }
    Refresh-Path
}
function Find-Python {
    foreach ($candidate in @('py','python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $prefix = @(); if ($candidate -eq 'py') { $prefix = @('-3') }
        try {
            $found = & $command.Source @prefix -c 'import sys; print(sys.executable) if sys.version_info >= (3,10) else sys.exit(1)' 2>$null
        } catch { continue } # Broken launcher/Store alias: try the next interpreter.
        if ($LASTEXITCODE -eq 0 -and $found) { return [string]($found | Select-Object -Last 1) }
    }
    return $null
}
try {
    if ($ClientArgs[0] -eq 'setup') {
        Write-Host 'Setup installs missing Python, Node.js, PowerShell 7 and OpenCode V2. Existing installations are preserved.'
        Write-Host 'System installers may require your UAC approval. CUA/REA setup follows.'
        $python = Find-Python
        if (-not $python) { Install-PackageId 'Python.Python.3.12'; $python = Find-Python }
        $nodeReady = $false
        if (Get-Command node -ErrorAction SilentlyContinue) {
            $nodeText = & node -p process.versions.node
            if ($LASTEXITCODE -eq 0) {
                $nodeVersion = [version]$nodeText
                $nodeReady = ($nodeVersion.Major -eq 22 -and $nodeVersion.Minor -ge 19) -or ($nodeVersion.Major -eq 24 -and $nodeVersion.Minor -ge 11) -or $nodeVersion.Major -ge 26
            }
        }
        if (-not $nodeReady) {
            if (Get-Command node -ErrorAction SilentlyContinue) { throw 'Existing Node.js is too old for REA. Upgrade to supported Node 24 LTS, then rerun setup; no existing runtime was replaced.' }
            Install-PackageId 'OpenJS.NodeJS.LTS'
        }
        if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node/npm is not available after installation. Reopen START-AGENT.bat and choose first setup again.' }
        if (-not (Get-Command pwsh -ErrorAction SilentlyContinue)) { Install-PackageId 'Microsoft.PowerShell' }
        if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
            $npm = Get-Command npm.cmd -ErrorAction Stop
            & $npm.Source install --global '@opencode/cli@2.0.22'
            if ($LASTEXITCODE -ne 0) { throw 'OpenCode V2 installation failed.' }
            Refresh-Path
        }
    }
    $python = Find-Python
    if (-not $python) { throw 'Python 3.10+ is missing. Run this entry point with setup first.' }
    & $python (Join-Path $PSScriptRoot 'setup_client.py') @ClientArgs
    exit $LASTEXITCODE
} catch { Write-Host "Setup stopped: $($_.Exception.Message)" -ForegroundColor Red; exit 2 }
