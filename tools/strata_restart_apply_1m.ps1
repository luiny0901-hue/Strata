# Restart the managed 1M Strata server once so the launcher regenerates the
# profile from the templates (prefill auto:16384, vram reserve 1216) and verify
# the live engine argv, GPU placement and one authenticated completion.
$ErrorActionPreference = 'Stop'
$stateDir = 'C:\Users\luiny\Strata-data\supervisor'
$gpuUuid = 'GPU-1f5cc5f8-41f5-0817-46b1-548cf1357b8d'
$apiKey = (Get-Content 'C:\Users\luiny\.config\strata\STRATA_API_KEY' -Raw).Trim()

$supervisors = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'strata_server_supervisor\.py' })
if (-not $supervisors.Count) { throw 'no running supervisor found' }
$ids = @($supervisors | ForEach-Object { [int]$_.ProcessId })
$roots = @($supervisors | Where-Object { $_.ParentProcessId -notin $ids })
if ($roots.Count -ne 1) { throw "expected one supervisor root; found $($roots.Count)" }
$root = $roots[0]
$commandLine = [string]$root.CommandLine
if ($commandLine -notmatch 'run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on-1m\.bat') { throw "root supervisor is not the 1M launcher: $commandLine" }

# the live server must be idle before we take it down
$status = Invoke-RestMethod 'http://127.0.0.1:8080/v1/status' -Headers @{ Authorization = "Bearer $apiKey" } -TimeoutSec 8
if ($status.activity.in_flight -ne 0) { throw 'server has an active request; retry the restart when idle' }

Write-Output "stopping supervisor root PID $($root.ProcessId)"
& taskkill.exe /PID $root.ProcessId /T /F | Out-Null
$deadline = [DateTime]::UtcNow.AddSeconds(180)
while ([DateTime]::UtcNow -lt $deadline) {
    $listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    $engine = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
    if (-not $listener -and -not $engine.Count) { break }
    Start-Sleep -Seconds 2
}
if ((Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) -or @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue).Count) {
    throw 'port 8080 or engine still active after stop'
}
Start-Sleep -Seconds 12

$started = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $commandLine; CurrentDirectory = 'C:\Users\luiny\Strata' }
if ($started.ReturnValue -ne 0) { throw "WMI could not start supervisor (return $($started.ReturnValue))" }
Write-Output "supervisor start requested PID $($started.ProcessId)"

$ready = $null
$deadline = [DateTime]::UtcNow.AddMinutes(30)
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 5
        if ($health.loaded -and $health.model -like '*qwen3.8-flash-next-unsloth-ud-iq4_xs*') { $ready = $health; break }
    } catch {}
    Start-Sleep -Seconds 5
}
if (-not $ready) { throw 'server did not become ready within 30 minutes' }

$engineProc = Get-CimInstance Win32_Process -Filter "Name='strata.exe'"
if (-not $engineProc) { throw 'engine process not found after ready' }
if ($engineProc.CommandLine -notmatch '--prefill\s+auto:16384') { throw "engine argv is missing prefill auto:16384: $($engineProc.CommandLine)" }
if ($engineProc.CommandLine -notmatch '--vram-reserve-mib\s+1216') { throw 'engine argv is missing vram reserve 1216' }

$rows = & nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader
$mine = @($rows | Where-Object { $_ -match ",\s*$($engineProc.ProcessId)," })
if ($mine.Count -ne 1 -or $mine[0] -notlike "$gpuUuid*") { throw "engine PID $($engineProc.ProcessId) is not confined to GPU 1 ($gpuUuid): $($mine -join '; ')" }

$profileJson = Get-Content 'C:\Users\luiny\AppData\Local\Strata\profiles\strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-on-1m.json' -Raw | ConvertFrom-Json
$pargs = $profileJson.args
if ($pargs[$pargs.IndexOf('--prefill') + 1] -ne 'auto:16384') { throw 'rendered profile prefill is wrong' }
if ($pargs[$pargs.IndexOf('--vram-reserve-mib') + 1] -ne '1216') { throw 'rendered profile reserve is wrong' }

$body = @{ model = 'strata'; messages = @(@{ role = 'user'; content = 'Reply with exactly: APPLY-OK' }); max_tokens = 16; temperature = 0; stream = $false; chat_template_kwargs = @{ enable_thinking = $false } } | ConvertTo-Json -Depth 5
$reply = Invoke-RestMethod 'http://127.0.0.1:8080/v1/chat/completions' -Method Post -ContentType 'application/json' -Headers @{ Authorization = "Bearer $apiKey" } -Body $body -TimeoutSec 300
if (-not $reply.choices -or -not $reply.choices.Count) { throw 'completion probe returned no choices' }

$newestLog = Get-ChildItem 'C:\Users\luiny\Strata-data\logs\strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-on-1m.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$tail = Get-Content -LiteralPath $newestLog.FullName -Tail 120 | Out-String
if ($tail -match 'illegal memory access|CUDA error') { throw 'engine log shows a GPU error after restart' }
$belowNote = if ($tail -match 'below 1024') { 'YES' } else { 'NO' }

Write-Output "HEALTH=$(($ready | Select-Object status, loaded, model, max_context | ConvertTo-Json -Compress))"
Write-Output "ENGINE_PID=$($engineProc.ProcessId) PREFILL=auto:16384 RESERVE=1216 GPU=1"
Write-Output "PROBE_REPLY=$($reply.choices[0].message.content)"
Write-Output "BELOW_1024_NOTE=$belowNote"
Write-Output 'APPLY_OK'
