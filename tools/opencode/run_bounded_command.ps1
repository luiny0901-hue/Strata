[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Command,

    [string]$WorkingDirectory = (Get-Location).Path,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 900,

    [ValidateRange(1, 300)]
    [int]$HeartbeatSeconds = 15,

    [string]$LogDirectory = (Join-Path $env:TEMP 'OpenCode-command-logs')
)

$ErrorActionPreference = 'Stop'
$resolvedDirectory = (Resolve-Path -LiteralPath $WorkingDirectory).Path
$null = New-Item -ItemType Directory -Path $LogDirectory -Force
$logId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMddTHHmmssfff'), [guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path $LogDirectory "$logId.stdout.log"
$stderrPath = Join-Path $LogDirectory "$logId.stderr.log"
$shell = (Get-Command pwsh -ErrorAction Stop).Source

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
foreach ($argument in @('-NoLogo', '-NoProfile', '-NonInteractive', '-Command')) {
    $startInfo.ArgumentList.Add($argument)
}
$startInfo.ArgumentList.Add($Command + [Environment]::NewLine + 'exit $LASTEXITCODE')

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $startInfo
if (-not $process.Start()) {
    [Console]::Error.WriteLine('ERROR: command process did not start.')
    exit 126
}
$process.StandardInput.Close()
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$nextHeartbeat = $HeartbeatSeconds
$timedOut = $false

while (-not $process.WaitForExit(1000)) {
    if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
        $timedOut = $true
        try {
            $process.Kill($true)
            $null = $process.WaitForExit(15000)
        }
        catch [System.InvalidOperationException] {
            # The process exited between the timeout check and Kill().
        }
        break
    }
    if ($timer.Elapsed.TotalSeconds -ge $nextHeartbeat) {
        [Console]::Out.WriteLine('[runner] still running elapsed={0}s pid={1}' -f [int]$timer.Elapsed.TotalSeconds, $process.Id)
        [Console]::Out.Flush()
        $nextHeartbeat += $HeartbeatSeconds
    }
}

$process.WaitForExit()
$timer.Stop()
$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($stdoutPath, $stdout, $utf8)
[System.IO.File]::WriteAllText($stderrPath, $stderr, $utf8)

function Write-Preview([string]$Text, [ValidateSet('Out', 'Error')][string]$Target) {
    if ([string]::IsNullOrEmpty($Text)) { return }
    $stream = [Console]::Out
    if ($Target -eq 'Error') { $stream = [Console]::Error }
    $limit = 24000
    if ($Text.Length -gt $limit) {
        $stream.WriteLine('[runner] output preview is truncated; full output is in the log file.')
        $Text = $Text.Substring($Text.Length - $limit)
    }
    $stream.Write($Text)
    if (-not $Text.EndsWith([Environment]::NewLine)) { $stream.WriteLine() }
}

Write-Preview $stdout Out
Write-Preview $stderr Error
[Console]::Out.WriteLine('ELAPSED_SECONDS={0:N1}' -f $timer.Elapsed.TotalSeconds)
[Console]::Out.WriteLine("LOG_STDOUT=$stdoutPath")
[Console]::Out.WriteLine("LOG_STDERR=$stderrPath")

if ($timedOut) {
    [Console]::Error.WriteLine("TIMEOUT_SECONDS=$TimeoutSeconds")
    [Console]::Error.WriteLine('PROCESS_TREE_TERMINATED=True')
    exit 124
}

[Console]::Out.WriteLine("EXIT_CODE=$($process.ExitCode)")
exit $process.ExitCode
