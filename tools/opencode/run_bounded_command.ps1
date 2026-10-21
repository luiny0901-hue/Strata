[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Text')]
    [ValidateNotNullOrEmpty()]
    [string]$Command,

    [Parameter(Mandatory = $true, ParameterSetName = 'File')]
    [string]$CommandFile,

    [switch]$RequireAdministrator,

    [string]$WorkingDirectory = (Get-Location).Path,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 900,

    [ValidateRange(1, 300)]
    [int]$HeartbeatSeconds = 15,

    [string]$LogDirectory = (Join-Path $env:TEMP 'OpenCode-command-logs')
)

$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
$resolvedDirectory = (Resolve-Path -LiteralPath $WorkingDirectory).Path
if (-not (Test-Path -LiteralPath $resolvedDirectory -PathType Container)) { throw 'WorkingDirectory must be a directory.' }
$shellInfo = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $shellInfo) { [Console]::Error.WriteLine('PWSH_REQUIRED: install PowerShell 7; no command started.'); exit 127 }
$shell = $shellInfo.Source
if ($RequireAdministrator) {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { [Console]::Error.WriteLine('BLOCKED_UAC: administrator rights required; no command started and no elevation prompt opened.'); exit 77 }
}
$body = $Command
$source = $Command
if ($PSCmdlet.ParameterSetName -eq 'File') {
    $resolvedFile = (Resolve-Path -LiteralPath $CommandFile).Path
    if (-not (Test-Path -LiteralPath $resolvedFile -PathType Leaf)) { throw 'CommandFile must be a file.' }
    $source = [System.IO.File]::ReadAllText($resolvedFile, [System.Text.Encoding]::UTF8)
    $body = "& '" + $resolvedFile.Replace("'", "''") + "'"
}
. (Join-Path $PSScriptRoot 'powershell-preflight.ps1')
$preflight = Get-OpenCodeCommandPreflight $source
if ($preflight -eq 77) { [Console]::Error.WriteLine('BLOCKED_UAC: elevation request refused before execution.'); exit 77 }
if ($preflight -ne 0) { [Console]::Error.WriteLine('COMMAND_PARSE_ERROR: no command started.'); exit $preflight }
$null = New-Item -ItemType Directory -Path $LogDirectory -Force
$LogDirectory = (Resolve-Path -LiteralPath $LogDirectory).Path
$logId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMddTHHmmssfff'), [guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path $LogDirectory "$logId.stdout.log"
$stderrPath = Join-Path $LogDirectory "$logId.stderr.log"
$scriptPath = Join-Path $LogDirectory "$logId.command.ps1"
[System.IO.File]::WriteAllText($scriptPath, $body, $utf8)

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $shell
$startInfo.WorkingDirectory = $resolvedDirectory
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
$bootstrap = Join-Path $PSScriptRoot 'powershell-bootstrap.ps1'
$startInfo.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + $bootstrap + '" -CommandFile "' + $scriptPath + '"'
foreach ($entry in @{'CI'='true'; 'NO_COLOR'='1'; 'GIT_TERMINAL_PROMPT'='0'; 'GCM_INTERACTIVE'='Never'; 'PYTHONIOENCODING'='utf-8'; 'PYTHONUNBUFFERED'='1'}.GetEnumerator()) {
    $startInfo.EnvironmentVariables[$entry.Key] = $entry.Value
}

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $startInfo
try {
    $stdoutLog = [System.IO.File]::Create($stdoutPath)
    $stderrLog = [System.IO.File]::Create($stderrPath)
} catch {
    if ($stdoutLog) { $stdoutLog.Dispose() }
    Remove-Item -LiteralPath $scriptPath -Force
    [Console]::Error.WriteLine('LOG_SETUP_FAILED: no command started.')
    exit 73
}
try { $started = $process.Start() } catch { $started = $false; [Console]::Error.WriteLine($_.ToString()) }
if (-not $started) {
    $stdoutLog.Dispose()
    $stderrLog.Dispose()
    Remove-Item -LiteralPath $scriptPath -Force
    [Console]::Error.WriteLine('ERROR: command process did not start; no retry was performed.')
    exit 126
}
$process.StandardInput.Close()
[Console]::Out.WriteLine(('[runner] started pid={0} timeout={1}s cwd={2}' -f $process.Id, $TimeoutSeconds, $resolvedDirectory))
[Console]::Out.Flush()
$stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutLog)
$stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrLog)
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$nextHeartbeat = $HeartbeatSeconds
$timedOut = $false
$treeTerminated = $false

while (-not $process.WaitForExit(1000)) {
    if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
        $timedOut = $true
        try {
            if ($PSVersionTable.PSVersion.Major -ge 7) { $process.Kill($true) }
            else { & "$env:WINDIR\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null }
            $treeTerminated = $process.WaitForExit(15000)
        }
        catch [System.InvalidOperationException] {
            # The process exited between the timeout check and Kill().
            $treeTerminated = $process.HasExited
        }
        catch { [Console]::Error.WriteLine('CLEANUP_REQUIRED: owned process termination failed; do not rerun the command.') }
        break
    }
    if ($timer.Elapsed.TotalSeconds -ge $nextHeartbeat) {
        [Console]::Out.WriteLine(('[runner] still running elapsed={0}s pid={1}' -f [int]$timer.Elapsed.TotalSeconds, $process.Id))
        [Console]::Out.Flush()
        $nextHeartbeat += $HeartbeatSeconds
    }
}

$timer.Stop()
$drained = $false
try {
    $drained = [System.Threading.Tasks.Task]::WhenAll([System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)).Wait(5000)
} catch { [Console]::Error.WriteLine('OUTPUT_DRAIN_ERROR: captured output may be incomplete.') }
$process.StandardOutput.Dispose()
$process.StandardError.Dispose()
$stdoutLog.Dispose()
$stderrLog.Dispose()
Remove-Item -LiteralPath $scriptPath -Force

function Write-Preview([string]$Path, [ValidateSet('Out', 'Error')][string]$Target) {
    $stream = [Console]::Out
    if ($Target -eq 'Error') { $stream = [Console]::Error }
    $limit = 24000
    $file = [System.IO.File]::OpenRead($Path)
    try {
        $null = $file.Seek([Math]::Max(0, $file.Length - 96000), [System.IO.SeekOrigin]::Begin)
        $bytes = New-Object byte[] ([int]($file.Length - $file.Position))
        $read = $file.Read($bytes, 0, $bytes.Length)
        $Text = [System.Text.Encoding]::UTF8.GetString($bytes, 0, $read)
    } finally { $file.Dispose() }
    if ($Text.Length -gt $limit) {
        $stream.WriteLine('[runner] output preview is truncated; full output is in the log file.')
        $Text = $Text.Substring($Text.Length - $limit)
    }
    $stream.Write($Text)
    if (-not $Text.EndsWith([Environment]::NewLine)) { $stream.WriteLine() }
}

Write-Preview $stdoutPath Out
Write-Preview $stderrPath Error
[Console]::Out.WriteLine('ELAPSED_SECONDS={0:N1}' -f $timer.Elapsed.TotalSeconds)
[Console]::Out.WriteLine("LOG_STDOUT=$stdoutPath")
[Console]::Out.WriteLine("LOG_STDERR=$stderrPath")
if (-not $drained) {
    [Console]::Error.WriteLine('OUTPUT_DRAIN_COMPLETE=False: inherited output handles did not close; logs may be incomplete. No automatic rerun.')
    exit 125
}

if ($timedOut) {
    [Console]::Error.WriteLine("TIMEOUT_SECONDS=$TimeoutSeconds")
    [Console]::Error.WriteLine("PROCESS_TREE_TERMINATED=$treeTerminated")
    if (-not $treeTerminated) { exit 125 }
    exit 124
}

[Console]::Out.WriteLine("EXIT_CODE=$($process.ExitCode)")
exit $process.ExitCode
