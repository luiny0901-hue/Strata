[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RegistryPath,
    [Parameter(Mandatory)][string]$Profile,
    [ValidateSet('Validate','Switch','Test')][string]$Mode = 'Switch'
)

$ErrorActionPreference = 'Stop'
$script:logPath = Join-Path $env:LOCALAPPDATA 'Strata\profile-switcher.log'
$script:mutex = $null
$script:oldCommandLine = $null
$script:oldWorkingDirectory = $null
$script:oldLauncher = $null
$script:oldExe = $null
$script:oldModel = $null
$script:oldStopped = $false
$script:targetLauncher = $null
$script:targetManagerPid = $null
$script:targetKept = $false
$script:targetPassed = $false
$script:restored = $false
$script:failure = $null
$script:apiKey = $null
$script:gpuIndex = $null
$script:port = $null
$script:bindHost = $null
$script:supervisor = $null
$script:entry = $null
$script:managedConfig = $null

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message`r`n"
    [System.IO.File]::AppendAllText($script:logPath, $line, [System.Text.UTF8Encoding]::new($false))
}
function Get-Property($Object, [string]$Name, $Default = $null) {
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $Default
}
function Assert-SafeLiteral([string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '["%!&|<>^\r\n]') {
        throw "$Label is empty or contains unsupported command-shell characters"
    }
}
function Get-GpuMap {
    $rows = & nvidia-smi --query-gpu=index,name,uuid,display_active --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi could not enumerate GPUs' }
    @($rows | Where-Object { $_.Trim() } | ForEach-Object {
        $p = $_.Split(',') | ForEach-Object { $_.Trim() }
        if ($p.Count -lt 4) { throw 'nvidia-smi returned an invalid GPU row' }
        [pscustomobject]@{ index=[int]$p[0]; name=$p[1]; uuid=$p[2]; display=$p[3] }
    })
}
function Get-Health {
    try { Invoke-RestMethod "http://127.0.0.1:$script:port/health" -TimeoutSec 5 } catch { $null }
}
function Get-Processes {
    @(Get-CimInstance Win32_Process -ErrorAction Stop)
}
function Get-DescendantIds([int]$RootId, $Processes) {
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    [void]$ids.Add($RootId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $Processes) {
            if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) { $changed = $true }
        }
    }
    $ids
}
function Get-ManagerRoots([string]$Launcher = $null) {
    $scriptPath = [IO.Path]::GetFullPath([string]$script:supervisor.script)
    $items = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf($scriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($null -eq $Launcher -or $_.CommandLine.IndexOf($Launcher, [StringComparison]::OrdinalIgnoreCase) -ge 0)
    })
    $ids = @($items | ForEach-Object { [int]$_.ProcessId })
    @($items | Where-Object { $_.ParentProcessId -notin $ids })
}
function Assert-SingleGpu([string]$EnginePath) {
    $gpu = Get-GpuMap | Where-Object { $_.index -eq $script:gpuIndex } | Select-Object -First 1
    if (-not $gpu -or $gpu.name -notlike '*RTX 3090 Ti*' -or $gpu.display -ne 'Disabled') {
        throw "GPU $script:gpuIndex is not the expected display-disabled RTX 3090 Ti"
    }
    $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" | Where-Object {
        [IO.Path]::GetFullPath($_.ExecutablePath) -ieq [IO.Path]::GetFullPath($EnginePath)
    })
    $allEngines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'")
    if ($engines.Count -ne 1 -or $allEngines.Count -ne 1) {
        throw "expected exactly one Strata engine process at $EnginePath; found $($allEngines.Count) total"
    }
    $rows = & nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi could not verify process-to-GPU placement' }
    $apps = @($rows | Where-Object { $_.Trim() } | ForEach-Object {
        $p = $_.Split(',') | ForEach-Object { $_.Trim() }
        if ($p.Count -ge 3) { [pscustomobject]@{ uuid=$p[0]; pid=[int]$p[1]; name=$p[2] } }
    })
    $bound = @($apps | Where-Object { $_.pid -eq $engines[0].ProcessId })
    if ($bound.Count -ne 1 -or $bound[0].uuid -ne $gpu.uuid) {
        throw "engine PID $($engines[0].ProcessId) is not confined to GPU $script:gpuIndex ($($gpu.uuid))"
    }
    Write-Log "GPU verified: index=$script:gpuIndex uuid=$($gpu.uuid) pid=$($engines[0].ProcessId)"
}
function Invoke-Probe {
    $body = @{ model='strata'; messages=@(@{role='user';content='Reply with OK.'}); max_tokens=2;
        chat_template_kwargs=@{enable_thinking=$false} } | ConvertTo-Json -Depth 5
    $response = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/chat/completions" -Method Post `
        -ContentType 'application/json' -Headers @{Authorization="Bearer $script:apiKey"} -Body $body -TimeoutSec 300
    if (-not $response.choices -or -not $response.choices.Count) { throw 'completion probe returned no choices' }
}
function Wait-PortAndEnginesDown([int]$Seconds = 180) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue
        $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
        if (-not $listener -and -not $engines.Count) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}
function Stop-ManagedLauncher([string]$Launcher) {
    $roots = @(Get-ManagerRoots $Launcher)
    if ($roots.Count -gt 1) { throw "multiple supervisor roots own launcher $Launcher" }
    if ($roots.Count -eq 1) {
        Write-Log "stopping verified supervisor root pid=$($roots[0].ProcessId)"
        & taskkill.exe /PID $roots[0].ProcessId /T /F 2>&1 | Out-Null
    }
    if (-not (Wait-PortAndEnginesDown)) { throw 'server port or engine stayed active; refusing the next launch' }
    Start-Sleep -Seconds 12
    Write-Log 'port and engine are down; unload interval passed'
}
function Start-Manager([string]$CommandLine, [string]$WorkingDirectory) {
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine=$CommandLine; CurrentDirectory=$WorkingDirectory
    }
    if ($result.ReturnValue -ne 0) { throw "WMI could not start supervisor (return $($result.ReturnValue))" }
    Write-Log "supervisor start requested pid=$($result.ProcessId)"
    [int]$result.ProcessId
}
function Wait-Ready([string]$ExpectedModel, [string]$ExpectedEngine, [int]$TimeoutSeconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $health = Get-Health
        if ($health -and $health.loaded -and $health.model -like "*$ExpectedModel*") {
            Assert-SingleGpu $ExpectedEngine
            Invoke-Probe
            Write-Log "health and completion probe passed: model=$($health.model), context=$($health.max_context)"
            return $health
        }
        Start-Sleep -Seconds 5
    }
    throw "server did not load the expected model '$ExpectedModel' within $TimeoutSeconds seconds"
}
function Quote-Argument([string]$Value) {
    Assert-SafeLiteral $Value 'argument'
    '"' + $Value + '"'
}

try {
    if (-not (Test-Path -LiteralPath $RegistryPath -PathType Leaf)) { throw "registry not found: $RegistryPath" }
    $registry = Get-Content -LiteralPath $RegistryPath -Raw | ConvertFrom-Json
    $script:supervisor = $registry.supervisor
    $script:entry = $registry.profiles.$Profile
    if (-not $script:entry) { throw "profile '$Profile' is not defined in the registry" }
    $script:gpuIndex = [int]$registry.gpu_index
    $script:port = [int]$registry.port
    $script:bindHost = [string]$registry.host
    if ($script:port -ne 8080) { throw 'this local managed workflow is pinned to port 8080' }
    if ($script:bindHost -notin @('0.0.0.0','127.0.0.1')) { throw 'host must be 0.0.0.0 or 127.0.0.1' }
    $script:apiKey = (Get-Content -LiteralPath $registry.api_key_file -Raw).Trim()
    if (-not $script:apiKey) { throw 'API key file is empty' }

    foreach ($item in @($script:supervisor.python,$script:supervisor.script,$script:supervisor.working_directory,
                        $script:supervisor.state_dir,$script:supervisor.token_file,$registry.api_key_file,
                        $script:entry.server_root,$script:entry.python,$script:entry.config)) {
        Assert-SafeLiteral ([string]$item) 'configured path'
    }
    foreach ($path in @($script:supervisor.python,$script:supervisor.script,$script:entry.python,
                        (Join-Path $script:entry.server_root 'serve\server.py'),$script:entry.config)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "required file not found: $path" }
    }
    if (-not (Test-Path -LiteralPath $script:supervisor.working_directory -PathType Container) -or
        -not (Test-Path -LiteralPath $script:supervisor.state_dir -PathType Container) -or
        -not (Test-Path -LiteralPath $script:supervisor.token_file -PathType Leaf) -or
        -not (Test-Path -LiteralPath $registry.api_key_file -PathType Leaf)) { throw 'supervisor or credential paths are not ready' }

    $config = Get-Content -LiteralPath $script:entry.config -Raw | ConvertFrom-Json
    $enginePath = [IO.Path]::GetFullPath([string]$config.exe)
    if (-not (Test-Path -LiteralPath $enginePath -PathType Leaf)) { throw "engine executable not found: $enginePath" }
    $modelName = [string](Get-Property $config 'model_name' '')
    if (-not $modelName) { throw 'profile config must declare model_name' }
    $engineArgs = @($config.args | ForEach-Object { [string]$_ })
    if (($engineArgs -join ' ') -match '(?i)(^|\s)--(layer-split|peer-device|tensor-split|split-mode|gpu-split)(\s|=|$)') {
        throw 'engine args contain a multi-GPU option; remove it from the selected profile'
    }
    if ($null -ne (Get-Property $config 'replicas') -and [int]$config.replicas -gt 1) {
        throw 'profile requests multiple server replicas'
    }
    $gpu = Get-GpuMap | Where-Object { $_.index -eq $script:gpuIndex } | Select-Object -First 1
    if (-not $gpu -or $gpu.name -notlike '*RTX 3090 Ti*' -or $gpu.display -ne 'Disabled') {
        throw "configured GPU $script:gpuIndex is not the display-disabled RTX 3090 Ti"
    }
    $script:mutex = [System.Threading.Mutex]::new($false, 'Local\StrataProfileSwitch')
    if (-not $script:mutex.WaitOne(0)) { throw 'another profile switch is already running' }
    $localRoot = Join-Path $env:LOCALAPPDATA 'Strata'
    if (-not (Test-Path -LiteralPath $localRoot -PathType Container)) { throw 'Local Strata data directory is missing' }
    $activeManagers = @(Get-ManagerRoots)
    if ($activeManagers.Count -ne 1) { throw "expected one managed supervisor root; found $($activeManagers.Count)" }
    $oldManager = $activeManagers[0]
    $script:oldCommandLine = [string]$oldManager.CommandLine
    if ($script:oldCommandLine -match '(?i)--launcher\s+"([^"]+)"') { $script:oldLauncher = $Matches[1] }
    elseif ($script:oldCommandLine -match '(?i)--launcher\s+(\S+)') { $script:oldLauncher = $Matches[1] }
    if (-not $script:oldLauncher) { throw 'could not identify the active supervisor launcher' }
    $script:oldWorkingDirectory = [string]$script:supervisor.working_directory
    $processes = Get-Processes
    $oldTree = Get-DescendantIds ([int]$oldManager.ProcessId) $processes
    $listener = Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener -or -not $oldTree.Contains([int]$listener.OwningProcess)) {
        throw '8080 is not owned by the verified managed supervisor tree'
    }
    $oldEngines = @($processes | Where-Object { $_.Name -eq 'strata.exe' -and $oldTree.Contains([int]$_.ProcessId) })
    if ($oldEngines.Count -ne 1) { throw "expected one engine in the current server tree; found $($oldEngines.Count)" }
    $script:oldExe = [IO.Path]::GetFullPath([string]$oldEngines[0].ExecutablePath)
    $healthOld = Get-Health
    if (-not $healthOld -or -not $healthOld.loaded) { throw 'current server is not loaded' }
    $script:oldModel = [string]$healthOld.model
    $status = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/status" -Headers @{Authorization="Bearer $script:apiKey"} -TimeoutSec 8
    if ($status.activity.in_flight -ne 0) { throw 'current server has an active request' }
    $connections = @(Get-NetTCPConnection -LocalPort $script:port -State Established -ErrorAction SilentlyContinue)
    if ($connections.Count) { throw "8080 has $($connections.Count) established client connection(s)" }
    Assert-SingleGpu $script:oldExe

    $profileDir = Join-Path $localRoot 'managed-profiles'
    $launcherDir = Join-Path $localRoot 'managed-launchers'
    [void][IO.Directory]::CreateDirectory($profileDir)
    [void][IO.Directory]::CreateDirectory($launcherDir)
    $safeName = $Profile -replace '[^A-Za-z0-9._-]','_'
    $hashInput = [Text.Encoding]::UTF8.GetBytes(([IO.Path]::GetFullPath($script:entry.config) + '|' + $modelName + '|' + $script:gpuIndex))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = ([BitConverter]::ToString($sha.ComputeHash($hashInput))).Replace('-','').Substring(0,12).ToLowerInvariant() }
    finally { $sha.Dispose() }
    $script:managedConfig = Join-Path $profileDir "$safeName-$hash.json"
    $script:targetLauncher = Join-Path $launcherDir "$safeName-$hash.bat"

    if ($config.PSObject.Properties.Name -contains 'gpu') { $config.gpu = $script:gpuIndex }
    else { $config | Add-Member -NotePropertyName gpu -NotePropertyValue $script:gpuIndex }
    if ($config.PSObject.Properties.Name -contains 'gpus_asked') { $config.gpus_asked = $true }
    else { $config | Add-Member -NotePropertyName gpus_asked -NotePropertyValue $true }
    foreach ($stale in @('gpu_roles','gpu_order','layer_split','gpu_none')) { $config.PSObject.Properties.Remove($stale) }
    if ($null -eq $config.vision) {
        $config | Add-Member -NotePropertyName vision -NotePropertyValue ([pscustomobject]@{gpu=$false})
    } elseif ($config.vision -isnot [pscustomobject]) { throw 'vision config must be a JSON object' }
    if ($config.vision.PSObject.Properties.Name -contains 'gpu') { $config.vision.gpu = $false }
    else { $config.vision | Add-Member -NotePropertyName gpu -NotePropertyValue $false }
    $managedJson = $config | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($script:managedConfig,$managedJson,[Text.UTF8Encoding]::new($false))

    $pathItems = @([IO.Path]::GetDirectoryName($enginePath)) + @($config.lib_dirs | ForEach-Object { [string]$_ })
    foreach ($item in @($pathItems) + @($script:entry.server_args)) { if ($item) { Assert-SafeLiteral ([string]$item) 'launcher value' } }
    $pathText = (@($pathItems | Select-Object -Unique) -join ';')
    $extraArgs = @($script:entry.server_args | ForEach-Object { Quote-Argument ([string]$_) }) -join ' '
    $launcherLines = @(
        '@echo off',
        'setlocal',
        'set "STRATA_API_KEY="',
        ('for /f "usebackq delims=" %%K in ("' + [string]$registry.api_key_file + '") do set "STRATA_API_KEY=%%K"'),
        'if not defined STRATA_API_KEY exit /b 24',
        ('set "PATH=' + $pathText + ';%PATH%"'),
        ('cd /d "' + [string]$script:entry.server_root + '" || exit /b 20'),
        ('"' + [string]$script:entry.python + '" -m serve.server --engine strata --config "' + $script:managedConfig + '" --host "' + $script:bindHost + '" --port ' + $script:port + ' ' + $extraArgs),
        'exit /b %ERRORLEVEL%'
    )
    [IO.File]::WriteAllText($script:targetLauncher,($launcherLines -join "`r`n")+"`r`n",[Text.UTF8Encoding]::new($false))

    $serverArgs = @('--launcher',(Quote-Argument $script:targetLauncher),'--state-dir',(Quote-Argument ([string]$script:supervisor.state_dir)),
        '--api-key-file',(Quote-Argument ([string]$registry.api_key_file)),'--token-file',(Quote-Argument ([string]$script:supervisor.token_file)),
        '--server-url',(Quote-Argument "http://127.0.0.1:$script:port"),'--console-log')
    if ($script:supervisor.sync_client_context -eq $true) { $serverArgs += '--sync-client-context' }
    $desktopConfig = [string](Get-Property $script:supervisor 'desktop_restart_config' '')
    if ($desktopConfig -and (Test-Path -LiteralPath $desktopConfig -PathType Leaf)) {
        $serverArgs += @('--desktop-restart-config',(Quote-Argument $desktopConfig))
    }
    $targetCommand = (Quote-Argument ([string]$script:supervisor.python)) + ' ' +
        (Quote-Argument ([string]$script:supervisor.script)) + ' ' + ($serverArgs -join ' ')
    if ($Mode -eq 'Validate') {
        $script:targetPassed = $true
        Write-Log "profile validated without changing the server: profile=$Profile model=$modelName GPU=$script:gpuIndex uuid=$($gpu.uuid)"
    } else {
        Write-Log "preflight passed: profile=$Profile model=$modelName GPU=$script:gpuIndex uuid=$($gpu.uuid) mode=$Mode"
        $script:oldStopped = $true
        Stop-ManagedLauncher $script:oldLauncher
        $script:targetManagerPid = Start-Manager $targetCommand ([string]$script:supervisor.working_directory)
        $readyTimeout = [int](Get-Property $script:entry 'ready_timeout_seconds' 1800)
        Wait-Ready $modelName $enginePath $readyTimeout | Out-Null
        $script:targetPassed = $true
        if ($Mode -eq 'Switch') {
            $script:targetKept = $true
            Write-Log "switch completed; target profile remains active: $Profile"
        } else {
            Write-Log "smoke test passed; preparing restoration of previous profile: $script:oldModel"
        }
    }
}
catch {
    $script:failure = $_.Exception.Message
    try { Write-Log "operation failed: $script:failure" } catch {}
}
finally {
    if ($script:oldStopped -and -not $script:targetKept) {
        try {
            $health = Get-Health
            $roots = @(Get-ManagerRoots)
            $oldEngines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue | Where-Object {
                [IO.Path]::GetFullPath($_.ExecutablePath) -ieq $script:oldExe
            })
            if ($health -and $health.loaded -and $health.model -like "*$script:oldModel*" -and $roots.Count -eq 1 -and $oldEngines.Count -eq 1) {
                Assert-SingleGpu $script:oldExe
                Invoke-Probe
                $script:restored = $true
                Write-Log 'previous server remained active and was verified; no duplicate supervisor started'
            } else {
                if ($script:targetLauncher) { Stop-ManagedLauncher $script:targetLauncher }
                elseif (-not (Wait-PortAndEnginesDown)) { throw 'server remained active; rollback launch refused' }
                $listeners = @(Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue)
                $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
                if ($listeners.Count -or $engines.Count) { throw 'an unowned listener or engine remains; rollback launch refused' }
                $restoreResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
                    CommandLine=$script:oldCommandLine; CurrentDirectory=$script:oldWorkingDirectory
                }
                if ($restoreResult.ReturnValue -ne 0) { throw "previous supervisor restore failed (return $($restoreResult.ReturnValue))" }
                Write-Log "previous supervisor restore requested pid=$($restoreResult.ProcessId)"
                $timeout = [int](Get-Property $script:supervisor 'restore_timeout_seconds' 1800)
                $deadline = [DateTime]::UtcNow.AddSeconds($timeout)
                while ([DateTime]::UtcNow -lt $deadline) {
                    $health = Get-Health
                    if ($health -and $health.loaded -and $health.model -like "*$script:oldModel*") {
                        Assert-SingleGpu $script:oldExe
                        Invoke-Probe
                        $roots = @(Get-ManagerRoots)
                        if ($roots.Count -ne 1) { throw "restored service has $($roots.Count) supervisor roots" }
                        $script:restored = $true
                        Write-Log "previous profile restored and verified: model=$($health.model), engine=$script:oldExe"
                        break
                    }
                    Start-Sleep -Seconds 5
                }
                if (-not $script:restored) { throw 'previous server did not become ready before the restore deadline' }
            }
        }
        catch {
            try { Write-Log "ROLLBACK FAILED: $($_.Exception.Message)" } catch {}
        }
    } elseif ($script:targetKept) {
        $script:restored = $true
    }
    if ($script:mutex) {
        try { $script:mutex.ReleaseMutex() } catch {}
        $script:mutex.Dispose()
    }
    try { Write-Log "finished: mode=$Mode target_passed=$script:targetPassed kept=$script:targetKept restored=$script:restored" } catch {}
}

if ($script:failure) {
    [Console]::Error.WriteLine("Profile switch failed: $script:failure; restored=$script:restored; log=$script:logPath")
    exit 1
}
if ($Mode -eq 'Validate') {
    if (-not $script:targetPassed) {
        [Console]::Error.WriteLine("Profile validation failed; log=$script:logPath")
        exit 4
    }
    [Console]::WriteLine("Profile validated without changing the server: profile=$Profile; GPU=$script:gpuIndex; log=$script:logPath")
    exit 0
}
if ($Mode -eq 'Test' -and (-not $script:targetPassed -or -not $script:restored)) {
    [Console]::Error.WriteLine("Profile test did not pass or restore; log=$script:logPath")
    exit 2
}
if ($Mode -eq 'Switch' -and -not $script:targetKept) {
    [Console]::Error.WriteLine("Profile switch did not leave the target active; restored=$script:restored; log=$script:logPath")
    exit 3
}
[Console]::WriteLine("Profile $Mode completed: profile=$Profile; model verified; GPU=$script:gpuIndex; log=$script:logPath")
exit 0
