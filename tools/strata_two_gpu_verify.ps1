# Verify the default-context ON/OFF layer-split launchers, then restore the exact server found at startup.
$ErrorActionPreference = 'Stop'
$batRoot = 'C:\Users\luiny\Strata'
$dataRoot = Join-Path $env:USERPROFILE 'Strata-data'
$model = 'qwen3.8-flash-next-unsloth-ud-iq4_xs'
$gpu0Uuid = 'GPU-fc1bef3e-abe7-a621-cfce-c28dddc92905'
$gpu1Uuid = 'GPU-1f5cc5f8-41f5-0817-46b1-548cf1357b8d'
$activeLauncher = $null
$restored = $false

function Get-SupervisorRoots([string]$launcher = '') {
    $items = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -match 'strata_server_supervisor\.py' -and
        (-not $launcher -or $_.CommandLine.IndexOf($launcher, [StringComparison]::OrdinalIgnoreCase) -ge 0)
    })
    $ids = @($items | ForEach-Object { [int]$_.ProcessId })
    @($items | Where-Object { $_.ParentProcessId -notin $ids })
}

function Get-DescendantIds([int]$rootId) {
    $processes = @(Get-CimInstance Win32_Process)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    [void]$ids.Add($rootId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $processes) {
            if ($ids.Contains([int]$process.ParentProcessId) -and $ids.Add([int]$process.ProcessId)) {
                $changed = $true
            }
        }
    }
    $ids
}

function Get-ServerSnapshot {
    $health = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 5
    if (-not $health.loaded -or $health.model -ne $model) { throw 'the existing server is not the expected loaded model' }
    $roots = @(Get-SupervisorRoots)
    if ($roots.Count -ne 1) { throw "expected one existing supervisor; found $($roots.Count)" }
    $root = $roots[0]
    $processes = @(Get-CimInstance Win32_Process)
    $tree = Get-DescendantIds ([int]$root.ProcessId)
    $listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener -or -not $tree.Contains([int]$listener.OwningProcess)) {
        throw 'port 8080 is not owned by the verified supervisor'
    }
    # The agent session runs on this same server, so its last request can still be finishing: wait briefly.
    $idleDeadline = [DateTime]::UtcNow.AddSeconds(240)
    while ($true) {
        $status = Invoke-RestMethod 'http://127.0.0.1:8080/v1/status' -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
        $connections = @(Get-NetTCPConnection -LocalPort 8080 -State Established -ErrorAction SilentlyContinue)
        if ($status.activity.in_flight -eq 0 -and -not $connections.Count) { break }
        if ([DateTime]::UtcNow -ge $idleDeadline) { throw 'the existing server stayed busy for 240 seconds; refusing to stop it' }
        Write-Output 'waiting for the existing server to go idle before stopping it'
        Start-Sleep -Seconds 10
    }
    $commandLine = [string]$root.CommandLine
    if ($commandLine -match '(?i)--launcher\s+"([^"]+)"') { $launcher = $Matches[1] }
    elseif ($commandLine -match '(?i)--launcher\s+(\S+)') { $launcher = $Matches[1] }
    else { throw 'could not identify the existing server launcher' }
    [pscustomobject]@{
        health = $health
        command_line = $commandLine
        working_directory = Split-Path -Parent $launcher
        launcher = $launcher
        root_pid = [int]$root.ProcessId
    }
}

function Stop-Server([string]$launcher) {
    $roots = @(Get-SupervisorRoots $launcher)
    if ($roots.Count -gt 1) { throw "multiple supervisor roots match launcher $launcher" }
    if ($roots.Count -eq 1) {
        $health = $null
        try { $health = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 5 } catch {}
        if ($health -and $health.loaded) {
            $status = Invoke-RestMethod 'http://127.0.0.1:8080/v1/status' -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
            if ($status.activity.in_flight -ne 0) { throw 'server is processing a request; refusing to stop it' }
        }
        Write-Output "stopping verified supervisor PID $($roots[0].ProcessId)"
        & taskkill.exe /PID $roots[0].ProcessId /T /F 2>&1 | Out-Null
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        $listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
        $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
        $allRoots = @(Get-SupervisorRoots)
        if (-not $listener -and -not $engines.Count -and -not $allRoots.Count) { break }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    $listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
    $allRoots = @(Get-SupervisorRoots)
    if ($listener -or $engines.Count -or $allRoots.Count) {
        throw "refusing to continue while server processes remain: listeners=$(@($listener).Count), engines=$($engines.Count), supervisors=$($allRoots.Count)"
    }
    Start-Sleep -Seconds 12
}

function Start-Bat([string]$name) {
    $path = Join-Path $batRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "launcher is missing: $path" }
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = 'cmd.exe /d /s /c ""' + $path + '" --managed"'
        CurrentDirectory = $batRoot
    }
    if ($result.ReturnValue -ne 0) { throw "WMI could not start $name (return $($result.ReturnValue))" }
    $script:activeLauncher = $path
    Write-Output "started $name"
}

function Wait-Ready([string]$launcher, [int]$expectedContext, [int]$timeoutSeconds = 900) {
    $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
    $started = [DateTime]::UtcNow
    $sawSupervisor = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $roots = @(Get-SupervisorRoots $launcher)
        if ($roots.Count -gt 1) { throw "multiple supervisor roots started for $launcher" }
        if ($roots.Count -eq 1) { $sawSupervisor = $true }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 5
            if ($health.loaded -and $health.model -eq $model -and $health.max_context -eq $expectedContext) {
                if (-not $sawSupervisor) { throw 'health response is not owned by the new supervisor' }
                return $health
            }
        } catch {
            if ($sawSupervisor -and -not $roots.Count) {
                throw "supervisor for $launcher exited before the expected profile became ready; inspect $dataRoot\supervisor\server.log"
            }
        }
        if (-not $roots.Count -and [DateTime]::UtcNow -gt $started.AddSeconds(25)) {
            throw "supervisor for $launcher did not remain active; inspect $dataRoot\supervisor\server.log"
        }
        Start-Sleep -Seconds 3
    }
    throw "server did not load context $expectedContext within $timeoutSeconds seconds"
}

function Invoke-Probe([string]$tag) {
    $body = @{ model = 'strata'; messages = @(@{ role = 'user'; content = 'Reply with exactly: TWO-GPU-OK' });
        max_tokens = 16; temperature = 0; stream = $false;
        chat_template_kwargs = @{ enable_thinking = $false } } | ConvertTo-Json -Depth 5
    $reply = Invoke-RestMethod 'http://127.0.0.1:8080/v1/chat/completions' -Method Post -ContentType 'application/json' `
        -Headers @{ Authorization = "Bearer $script:apiKey" } -Body $body -TimeoutSec 300
    if (-not [string]$reply.choices[0].message.content) { throw "$tag probe returned no text" }
    Write-Output "$tag completion probe passed"
}

function Test-Dual([string]$mode) {
    $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'")
    if ($engines.Count -ne 1) { throw "expected one engine for $mode; found $($engines.Count)" }
    $engine = $engines[0]
    if ($engine.CommandLine -notmatch '--layer-split') { throw "$mode engine is missing --layer-split" }
    if ($engine.CommandLine -match '--peer-device') { throw "$mode engine still carries --peer-device" }
    $rows = @(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader) |
        Where-Object { $_ -match ",\s*$($engine.ProcessId)," }
    $uuids = @($rows | ForEach-Object { ($_ -split ',')[0].Trim() } | Sort-Object -Unique)
    if ($uuids.Count -ne 2 -or $uuids -notcontains $gpu1Uuid -or $uuids -notcontains $gpu0Uuid) {
        throw "$mode engine did not run on both expected RTX 3090 Ti cards: $($uuids -join ' ')"
    }
    $log = Join-Path $dataRoot "logs\strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-$mode-2gpu.log"
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "$mode engine log is missing: $log" }
    # The engine log is appended across runs: judge only the lines the current start wrote.
    $startLine = @(Select-String -LiteralPath $log -SimpleMatch 'engine started:') | Select-Object -Last 1
    if (-not $startLine) { throw "$mode engine log has no engine start; inspect $log" }
    $current = @(Get-Content -LiteralPath $log | Select-Object -Skip $startLine.LineNumber)
    $bad = @($current | Where-Object { $_ -match 'illegal memory access|layer-split cannot|expert cache: no room|no VRAM is left' })
    if ($bad.Count) { throw "$mode engine log reports a split allocation/runtime error; inspect $log" }
    $cache = @($current | Where-Object { $_ -match 'expert cache \d+ slots|runs layers \d+-\d+' } | Select-Object -Last 3)
    $cache | ForEach-Object { Write-Output "  $_" }
    $gpus = @(nvidia-smi --query-gpu=index,uuid,display_active,memory.used,memory.free --format=csv,noheader,nounits |
        ForEach-Object { $p = $_.Split(',') | ForEach-Object { $_.Trim() }
            [pscustomobject]@{ index=[int]$p[0]; uuid=$p[1]; display=$p[2]; used_mib=[int]$p[3]; free_mib=[int]$p[4] } })
    $display = @($gpus | Where-Object { $_.uuid -eq $gpu0Uuid })[0]
    if ($display.display -ne 'Enabled' -or $display.used_mib -lt 1024) {
        throw "the layer split did not put its share of model memory on the display card: used=$($display.used_mib) MiB"
    }
    Write-Output ("engine $mode PID $($engine.ProcessId) on GPU 0 (display, used $($display.used_mib) MiB) + GPU 1 " +
        "(used $(@($gpus | Where-Object { $_.uuid -eq $gpu1Uuid })[0].used_mib) MiB); layers split across both")
}

try {
    $script:apiKey = (Get-Content (Join-Path $env:USERPROFILE '.config\strata\STRATA_API_KEY') -Raw).Trim()
    if (-not $script:apiKey) { throw 'Strata API key is empty' }
    $original = Get-ServerSnapshot
    Write-Output "existing server verified: context=$($original.health.max_context), launcher=$($original.launcher)"
    Stop-Server $original.launcher

    foreach ($mode in @('on', 'off')) {
        $name = "run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-$mode-2gpu.bat"
        Start-Bat $name
        $dualLauncher = Join-Path $batRoot $name
        $ready = Wait-Ready $dualLauncher 262144
        Test-Dual $mode
        Invoke-Probe "262K two-card $mode"
        Stop-Server $dualLauncher
        $script:activeLauncher = $null
    }
}
finally {
    if ($script:activeLauncher) {
        try { Stop-Server $script:activeLauncher; $script:activeLauncher = $null }
        catch { Write-Output "test server stop failed; refusing overlapping restoration: $($_.Exception.Message)" }
    }
    if ($original -and -not $script:activeLauncher) {
        $listeners = @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)
        $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
        $roots = @(Get-SupervisorRoots)
        if (-not $listeners.Count -and -not $engines.Count -and -not $roots.Count) {
            $restore = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
                CommandLine = $original.command_line; CurrentDirectory = $original.working_directory
            }
            if ($restore.ReturnValue -ne 0) { throw "could not restart the original supervisor (return $($restore.ReturnValue))" }
            $null = Wait-Ready $original.launcher ([int]$original.health.max_context)
            $state = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'")
            $gpuRows = @(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader) |
                Where-Object { $state.Count -eq 1 -and $_ -match ",\s*$($state[0].ProcessId)," }
            $gpuUuids = @($gpuRows | ForEach-Object { ($_ -split ',')[0].Trim() } | Sort-Object -Unique)
            if ($state.Count -ne 1 -or $state[0].CommandLine -match '--peer-device' -or
                $gpuUuids.Count -ne 1 -or $gpuUuids[0] -ne $gpu1Uuid) {
                throw "the original server did not restore on GPU 1 alone: $($gpuUuids -join ' ')"
            }
            Invoke-Probe 'restored original server'
            $script:restored = $true
            Write-Output "RESTORED_ORIGINAL_OK context=$($original.health.max_context) gpu=1"
        } else {
            Write-Output "refusing to launch the original server over remaining processes: listeners=$($listeners.Count), engines=$($engines.Count), supervisors=$($roots.Count)"
        }
    }
}
