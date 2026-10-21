param([Parameter(Mandatory = $true)][string]$CommandFile)
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
try {
    . (Join-Path $PSScriptRoot 'powershell-preflight.ps1')
    $path = (Resolve-Path -LiteralPath $CommandFile).Path
    $status = Get-OpenCodeCommandPreflight ([System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8))
    if ($status -eq 77) { [Console]::Error.WriteLine('BLOCKED_UAC: elevation request refused before execution.'); exit 77 }
    if ($status -ne 0) { [Console]::Error.WriteLine('COMMAND_PARSE_ERROR: no command executed.'); exit $status }
    & $path
    $succeeded = $?
    $nativeExit = $LASTEXITCODE
    if (-not $succeeded -and $nativeExit -eq 0) { exit 1 }
    exit $nativeExit
} catch {
    $exception = $_.Exception
    while ($exception) {
        if ($exception -is [System.ComponentModel.Win32Exception] -and $exception.NativeErrorCode -in @(740, 1223)) {
            [Console]::Error.WriteLine('BLOCKED_UAC: elevation was required or cancelled. Do not retry automatically.')
            exit 77
        }
        $exception = $exception.InnerException
    }
    [Console]::Error.WriteLine($_.ToString())
    exit 1
}
