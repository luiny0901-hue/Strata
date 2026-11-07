[CmdletBinding()]
param(
    [string]$RegistryPath = 'C:\Users\luiny\AppData\Local\Strata\profile-switcher.json',
    [string]$ProfileName = 'current-fork',
    [string]$ResultDirectory = (Join-Path $env:LOCALAPPDATA 'Strata\gpu-settings-benchmark'),
    [int]$WarmupTokens = 8,
    [int]$OutputTokens = 128,
    [int]$Rounds = 3,
    [int]$IdleTimeoutSeconds = 900,
    [string]$Scenarios = '',
    [int]$ColdPromptKilo = 0,
    [int]$ImageRounds = 0
)

$ErrorActionPreference = 'Stop'
$script:port = 8080
$script:bindHost = '0.0.0.0'
$script:apiKey = $null
$script:oldCommandLine = $null
$script:oldWorkingDirectory = $null
$script:oldModel = $null
$script:oldLauncher = $null
$script:restored = $false
$script:coldPromptKilo = $ColdPromptKilo
$script:restoreManagerPid = 0
$script:scenarioRoots = @{}
$script:activeScenario = $null

function Get-Property($Object, [string]$Name, $Default = $null) {
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $Default
}
function Write-Progress-Line([string]$Message) {
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $Message"
}
function Get-GpuMap {
    $rows = & nvidia-smi --query-gpu=index,name,uuid,display_active,memory.used,memory.free --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi could not enumerate GPUs' }
    @($rows | Where-Object { $_.Trim() } | ForEach-Object {
        $p = $_.Split(',') | ForEach-Object { $_.Trim() }
        [pscustomobject]@{ index = [int]$p[0]; name = $p[1]; uuid = $p[2]; display = $p[3]; used_mib = [int]$p[4]; free_mib = [int]$p[5] }
    })
}
function Get-Health {
    try { Invoke-RestMethod "http://127.0.0.1:$script:port/health" -TimeoutSec 5 } catch { $null }
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
function Assert-EnginePlacement([string]$EnginePath, [int[]]$AllowedGpuIndices, [bool]$AllowVisionOnGpu = $false, [int]$MaxEngines = 1) {
    $engineList = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" | Where-Object {
        [IO.Path]::GetFullPath($_.ExecutablePath) -ieq [IO.Path]::GetFullPath($EnginePath)
    })
    $allEngines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'")
    if ($engineList.Count -ne $MaxEngines -or $allEngines.Count -gt $MaxEngines) {
        throw "expected at most $MaxEngines Strata engine processes at $EnginePath; found $($allEngines.Count) total"
    }
    $gpuMap = @(Get-GpuMap)
    $allowed = @($gpuMap | Where-Object { $AllowedGpuIndices -contains $_.index })
    if (-not $allowed.Count -or @($allowed | Where-Object { $_.name -notlike '*RTX 3090 Ti*' }).Count) {
        throw "allowed GPU set is invalid: $($AllowedGpuIndices -join ',')"
    }
    $allowedUuids = @($allowed | ForEach-Object { $_.uuid })
    $rows = & nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi could not verify process placement' }
    $apps = @($rows | Where-Object { $_.Trim() } | ForEach-Object {
        $p = $_.Split(',') | ForEach-Object { $_.Trim() }
        if ($p.Count -ge 3) { [pscustomobject]@{ uuid = $p[0]; pid = [int]$p[1]; name = $p[2] } }
    })
    $engineIds = @($engineList | ForEach-Object { [int]$_.ProcessId })
    $bound = @($apps | Where-Object { $engineIds -contains $_.pid })
    $wrong = @($bound | Where-Object { $allowedUuids -notcontains $_.uuid })
    if (-not $bound.Count -or $wrong.Count) {
        throw "engine PID(s) $(($engineIds -join ',')) are not confined to allowed GPU(s) $($AllowedGpuIndices -join ',')"
    }
    $vision = @(Get-CimInstance Win32_Process -Filter "Name='strata-vision.exe'" | Where-Object {
        $ids = Get-DescendantIds ([int](Get-ManagerRoots | Select-Object -First 1 -ExpandProperty ProcessId)) (Get-CimInstance Win32_Process)
        $ids.Contains([int]$_.ProcessId)
    })
    $visionOnGpu = @()
    if ($vision.Count) {
        $visionIds = @($vision | ForEach-Object { [int]$_.ProcessId })
        $visionOnGpu = @($apps | Where-Object { $visionIds -contains $_.pid })
        if ($visionOnGpu.Count -and -not $AllowVisionOnGpu) { throw 'the picture encoder is on a GPU although its profile says gpu=false' }
        $badVision = @($visionOnGpu | Where-Object { $allowedUuids -notcontains $_.uuid })
        if ($badVision.Count) { throw 'the picture encoder runs on a GPU outside the allowed set' }
    }
    return [pscustomobject]@{
        allowed_gpu_indices = $AllowedGpuIndices; engine_gpu_uuids = @($bound | Select-Object -ExpandProperty uuid -Unique)
        display_active = @($allowed | Select-Object index,display); engine_pids = $engineIds; engine_on_gpu = $bound.Count
        vision_pids = @($vision | ForEach-Object { [int]$_.ProcessId }); vision_on_gpu_uuids = @($visionOnGpu | Select-Object -ExpandProperty uuid -Unique)
    }
}
function Wait-ServerIdle([int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ($true) {
        $health = Get-Health
        if (-not $health -or -not $health.loaded) { throw 'server is not ready for the benchmark' }
        $status = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/status" -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
        $connections = @(Get-NetTCPConnection -LocalPort $script:port -State Established -ErrorAction SilentlyContinue)
        if ($status.activity.in_flight -eq 0 -and -not $connections.Count) { return }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "server remained busy for $Seconds seconds; in_flight=$($status.activity.in_flight), connections=$($connections.Count)"
        }
        Start-Sleep -Seconds 10
    }
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
        Write-Progress-Line "stopping scenario supervisor PID $($roots[0].ProcessId)"
        & taskkill.exe /PID $roots[0].ProcessId /T /F 2>&1 | Out-Null
    }
    if (-not (Wait-PortAndEnginesDown)) { throw 'port or engine remained active after stopping the scenario' }
    Start-Sleep -Seconds 12
}
function Start-Manager([string]$CommandLine, [string]$WorkingDirectory) {
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $CommandLine; CurrentDirectory = $WorkingDirectory
    }
    if ($result.ReturnValue -ne 0) { throw "WMI could not start supervisor (return $($result.ReturnValue))" }
    [int]$result.ProcessId
}
function Quote-Argument([string]$Value) { '"' + $Value + '"' }
function Set-EngineArgument($ArgumentList, [string]$Name, $Value) {
    $index = $ArgumentList.IndexOf($Name)
    if ($index -lt 0) {
        $ArgumentList.Add($Name) | Out-Null
        if ($null -ne $Value) { $ArgumentList.Add([string]$Value) | Out-Null }
        return
    }
    if ($null -eq $Value) {
        if ($Name -in @('--kv','--kv-resident','--prefill','--vram-reserve-mib','--expert-cache','--peer-device')) {
            if ($index + 1 -ge $ArgumentList.Count) { throw "$Name has no value to remove" }
            $ArgumentList.RemoveAt($index + 1)
        }
        $ArgumentList.RemoveAt($index)
        return
    }
    if ($index + 1 -ge $ArgumentList.Count) { throw "$Name has no value to replace" }
    $ArgumentList[$index + 1] = [string]$Value
}
function New-ColdPromptText {
    $targetChars = $script:coldPromptKilo * 1024 * 4
    $line = 'Optimization probe passage 0123456789: the quick brown fox jumps over the lazy dog while the steady engine keeps its cache warm. '
    $builder = [Text.StringBuilder]::new()
    while ($builder.Length -lt $targetChars) { [void]$builder.Append($line) }
    return 'PROBE-77 sits at the start of this passage. ' + $builder.ToString() + ' After this passage, reply with exactly: PROBE-OK'
}
function New-TestImageBase64([int]$Seed, [int]$Pixels) {
    Add-Type -AssemblyName System.Drawing
    $random = [Random]::new($Seed)
    $bitmap = [Drawing.Bitmap]::new($Pixels, $Pixels, [Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.Clear([Drawing.Color]::FromArgb(240, 240, 240))
    for ($i = 0; $i -lt 240; $i++) {
        $brush = [Drawing.SolidBrush]::new([Drawing.Color]::FromArgb($random.Next(256), $random.Next(256), $random.Next(256)))
        $x = $random.Next($Pixels - 140); $y = $random.Next($Pixels - 140)
        $w = 20 + $random.Next(120); $h = 20 + $random.Next(120)
        $graphics.FillRectangle($brush, $x, $y, $w, $h)
        $brush.Dispose()
    }
    $graphics.Dispose()
    $stream = [IO.MemoryStream]::new()
    $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    $bytes = $stream.ToArray(); $stream.Dispose()
    [Convert]::ToBase64String($bytes)
}
function Invoke-ImageProbe([int]$Seed) {
    $imageBase64 = New-TestImageBase64 $Seed 1024
    $parameters = [ordered]@{
        model = 'strata'; max_tokens = 24; temperature = 0; stream = $false
        messages = @(@{ role = 'user'; content = @(
            @{ type = 'text'; text = 'Reply with exactly: VISION-OK' },
            @{ type = 'image_url'; image_url = @{ url = "data:image/png;base64,$imageBase64" } }
        ) })
        chat_template_kwargs = @{ enable_thinking = $false }
    }
    $body = ConvertTo-Json $parameters -Depth 8
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/chat/completions" -Method Post `
        -ContentType 'application/json' -Headers @{ Authorization = "Bearer $script:apiKey" } `
        -Body $body -TimeoutSec 600
    $sw.Stop()
    if (-not $response.choices -or -not $response.choices.Count) { throw 'image probe returned no choices' }
    $status = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/status" -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
    $timings = Get-Property $status 'last_timings' $null
    $decodeRate = if ($timings) { [double](Get-Property $timings 'predicted_per_second' 0) } else { 0 }
    $promptTokens = if ($timings) { [int](Get-Property $timings 'prompt_n' 0) } else { 0 }
    $cachedTokens = if ($timings) { [int](Get-Property $timings 'cache_n' 0) } else { 0 }
    $visionRows = @(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader | Where-Object { $_ -match 'strata-vision' })
    [pscustomobject]@{
        wall_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 3)
        decode_tokens_per_second = $decodeRate
        prompt_tokens = $promptTokens
        cached_prompt_tokens = $cachedTokens
        vision_gpu_rows = $visionRows
        text = [string]$response.choices[0].message.content
    }
}
function Get-CompletedJson([int]$Tokens, [bool]$Short = $false) {
    $content = if ($script:coldPromptKilo -gt 0 -and -not $Short) { New-ColdPromptText } else { 'Write one continuous paragraph explaining how predictable GPU memory use helps stable model inference. Continue until you reach the output limit; do not add a heading.' }
    $parameters = [System.Collections.Generic.Dictionary[string, object]]::new()
    $parameters['model'] = 'strata'
    $parameters['messages'] = @(@{ role = 'user'; content = $content })
    $parameters['max_tokens'] = $Tokens
    $parameters['temperature'] = 0
    $parameters['stream'] = $false
    $parameters['chat_template_kwargs'] = @{ enable_thinking = $false }
    ConvertTo-Json $parameters -Depth 6
}
function Invoke-TimedCompletion([int]$Tokens, [bool]$Short = $false) {
    $body = Get-CompletedJson $Tokens $Short
    $timeoutSeconds = if ($script:coldPromptKilo -gt 0 -and -not $Short) { 900 } else { 300 }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/chat/completions" -Method Post `
        -ContentType 'application/json' -Headers @{ Authorization = "Bearer $script:apiKey" } `
        -Body $body -TimeoutSec $timeoutSeconds
    $sw.Stop()
    if (-not $response.choices -or -not $response.choices.Count) { throw 'completion returned no choices' }
    $usage = Get-Property $response 'usage' $null
    $count = if ($usage) { [int](Get-Property $usage 'completion_tokens' 0) } else { 0 }
    $status = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/status" -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
    $timings = Get-Property $status 'last_timings' $null
    $decodeRate = if ($timings) { [double](Get-Property $timings 'predicted_per_second' 0) } else { 0 }
    $promptRate = if ($timings) { [double](Get-Property $timings 'prompt_per_second' 0) } else { 0 }
    $promptTokens = if ($timings) { [int](Get-Property $timings 'prompt_n' 0) } else { 0 }
    $cachedTokens = if ($timings) { [int](Get-Property $timings 'cache_n' 0) } else { 0 }
    if ($count -le 0) { $count = $Tokens }
    [pscustomobject]@{
        seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 6)
        completion_tokens = $count
        tokens_per_second = [Math]::Round($decodeRate, 3)
        prompt_tokens = $promptTokens
        prompt_tokens_per_second = [Math]::Round($promptRate, 1)
        cached_prompt_tokens = $cachedTokens
        wall_tokens_per_second = [Math]::Round($count / [Math]::Max($sw.Elapsed.TotalSeconds, 0.000001), 3)
        text = [string]$response.choices[0].message.content
    }
}
function Wait-Ready([string]$ExpectedModel, [string]$ExpectedEngine, [int[]]$AllowedGpuIndices, [int]$TimeoutSeconds, [int]$ManagerPid = 0, [string]$ExpectedConfig = '', [bool]$AllowVisionOnGpu = $false) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($ManagerPid -and -not (Get-Process -Id $ManagerPid -ErrorAction SilentlyContinue)) {
            throw "supervisor PID $ManagerPid exited before the profile became ready; inspect $($script:supervisor.state_dir)\server.log"
        }
        $health = Get-Health
        if ($health -and $health.loaded -and $health.model -like "*$ExpectedModel*") {
            if ($ExpectedConfig) {
                $listener = Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                $owner = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" } else { $null }
                if (-not $owner -or $owner.CommandLine.IndexOf($ExpectedConfig, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
                    Start-Sleep -Seconds 5
                    continue
                }
            }
            $placement = Assert-EnginePlacement $ExpectedEngine $AllowedGpuIndices $AllowVisionOnGpu
            $probe = Invoke-TimedCompletion 1 $true
            if (-not $probe.text) { throw 'model probe returned no text' }
            return @{ health = $health; placement = $placement }
        }
        Start-Sleep -Seconds 5
    }
    throw "server did not load expected model '$ExpectedModel' within $TimeoutSeconds seconds"
}

try {
    if (-not (Test-Path -LiteralPath $RegistryPath -PathType Leaf)) { throw "registry not found: $RegistryPath" }
    $registry = Get-Content -LiteralPath $RegistryPath -Raw | ConvertFrom-Json
    $script:supervisor = $registry.supervisor
    $profileEntry = $registry.profiles.$ProfileName
    if (-not $profileEntry) { throw "profile '$ProfileName' is not defined" }
    $script:port = [int]$registry.port
    $script:bindHost = [string]$registry.host
    $script:apiKey = (Get-Content -LiteralPath $registry.api_key_file -Raw).Trim()
    $config = Get-Content -LiteralPath $profileEntry.config -Raw | ConvertFrom-Json
    $enginePath = [IO.Path]::GetFullPath([string]$config.exe)
    $modelName = [string](Get-Property $config 'model_name' '')
    if (-not (Test-Path -LiteralPath $enginePath -PathType Leaf) -or -not $modelName) { throw 'profile engine or model name is unavailable' }
    [IO.Directory]::CreateDirectory($ResultDirectory) | Out-Null

    $activeManagers = @(Get-ManagerRoots)
    if ($activeManagers.Count -ne 1) { throw "expected one managed supervisor root; found $($activeManagers.Count)" }
    $oldManager = $activeManagers[0]
    $script:oldCommandLine = [string]$oldManager.CommandLine
    if ($script:oldCommandLine -match '(?i)--launcher\s+"([^"]+)"') { $script:oldLauncher = $Matches[1] }
    elseif ($script:oldCommandLine -match '(?i)--launcher\s+(\S+)') { $script:oldLauncher = $Matches[1] }
    $script:oldWorkingDirectory = [string]$script:supervisor.working_directory
    $processes = @(Get-CimInstance Win32_Process)
    $oldTree = Get-DescendantIds ([int]$oldManager.ProcessId) $processes
    $listener = Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener -or -not $oldTree.Contains([int]$listener.OwningProcess)) { throw '8080 is not owned by the verified supervisor' }
    $status = Invoke-RestMethod "http://127.0.0.1:$script:port/v1/status" -Headers @{ Authorization = "Bearer $script:apiKey" } -TimeoutSec 8
    if ($status.activity.in_flight -ne 0) { Write-Progress-Line "current server is busy; waiting up to $IdleTimeoutSeconds seconds before benchmark" }
    Wait-ServerIdle $IdleTimeoutSeconds
    $script:oldModel = [string](Get-Health).model
    Write-Progress-Line "current server verified idle: $script:oldModel"

    $baseArgs = [System.Collections.Generic.List[string]]::new()
    foreach ($item in @($config.args)) { $baseArgs.Add([string]$item) }
    $prompts = [ordered]@{
        'baseline-gpu1-current' = @{ gpu = 1; allowed = @(1); changes = @{} }
        'gpu0-current' = @{ gpu = 0; allowed = @(0); changes = @{} }
        'gpu-unlocked-auto' = @{ gpu = $null; allowed = @(0,1); changes = @{} }
        'prefill-16k-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--prefill' = 'auto:16384' } }
        'reserve-448-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--vram-reserve-mib' = '448' } }
        'prefill-16k-reserve-448-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--prefill' = 'auto:16384'; '--vram-reserve-mib' = '448' } }
        'prefill-16k-reserve-1216-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--prefill' = 'auto:16384'; '--vram-reserve-mib' = '1216' } }
        'kv-k8v4-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--kv' = 'k8v4' } }
        'kv-grow-gpu1' = @{ gpu = 1; allowed = @(1); changes = @{ '--kv-grow' = $null; '--kv-resident' = $null } }
        'peer-gpu0-gpu1' = @{ gpu = '1,0'; allowed = @(0,1); changes = @{ '--peer-device' = '1' } }
        'vision-gpu-1216-gpu1' = @{ gpu = 1; allowed = @(1); visionGpu = $true; changes = @{} }
        'vision-gpu-2048-gpu1' = @{ gpu = 1; allowed = @(1); visionGpu = $true; changes = @{ '--vram-reserve-mib' = '2048' } }
    }
    if (-not [string]::IsNullOrWhiteSpace($Scenarios)) {
        $selected = [ordered]@{}
        foreach ($scenarioName in ($Scenarios -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
            if (-not $prompts.Contains($scenarioName)) { throw "unknown benchmark scenario: $scenarioName" }
            $selected[$scenarioName] = $prompts[$scenarioName]
        }
        $prompts = $selected
    }

    $localRoot = Join-Path $env:LOCALAPPDATA 'Strata'
    $profileDir = Join-Path $localRoot 'benchmark-profiles'
    $launcherDir = Join-Path $localRoot 'benchmark-launchers'
    [IO.Directory]::CreateDirectory($profileDir) | Out-Null
    [IO.Directory]::CreateDirectory($launcherDir) | Out-Null

    $scenarioResults = [System.Collections.Generic.List[object]]::new()
    $startedAt = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $jsonPath = Join-Path $ResultDirectory "gpu-settings-$startedAt.json"
    foreach ($name in $prompts.Keys) {
        $scenario = $prompts[$name]
        $scenarioGpu = $scenario.gpu
        $visionOn = [bool]$scenario.visionGpu
        $scenarioArgs = [System.Collections.Generic.List[string]]::new($baseArgs)
        foreach ($key in $scenario.changes.Keys) { Set-EngineArgument $scenarioArgs ([string]$key) $scenario.changes[$key] }
        $testConfig = $config | ConvertTo-Json -Depth 100 | ConvertFrom-Json
        $testConfig.args = @($scenarioArgs)
        if ($null -eq $scenarioGpu) {
            $testConfig.PSObject.Properties.Remove('gpu')
            $testConfig.PSObject.Properties.Remove('gpus_asked')
        } else { $testConfig.gpu = $scenarioGpu }
        $testConfig.vision.gpu = $visionOn
        $testConfig.log = Join-Path $ResultDirectory "engine-$name.log"
        $safe = $name -replace '[^A-Za-z0-9._-]', '_'
        $managedConfig = Join-Path $profileDir "$safe.json"
        $launcher = Join-Path $launcherDir "$safe.bat"
        [IO.File]::WriteAllText($managedConfig, ($testConfig | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
        $engineDir = [IO.Path]::GetDirectoryName($enginePath)
        $libDirs = @($engineDir) + @($config.lib_dirs | ForEach-Object { [string]$_ })
        $pathText = (@($libDirs | Select-Object -Unique) -join ';')
        $launcherLines = @(
            '@echo off', 'setlocal',
            'set "STRATA_API_KEY="',
            ('for /f "usebackq delims=" %%K in ("' + [string]$registry.api_key_file + '") do set "STRATA_API_KEY=%%K"'),
            'if not defined STRATA_API_KEY exit /b 24',
            ('set "PATH=' + $pathText + ';%PATH%"'),
            ('set "PYTHONPATH=' + [string]$script:supervisor.working_directory + '\tools;%PYTHONPATH%"'),
            ('cd /d "' + [string]$profileEntry.server_root + '" || exit /b 20'),
            ('"' + [string]$profileEntry.python + '" -m serve.server --engine strata --config "' + $managedConfig + '" --host "' + $script:bindHost + '" --port ' + $script:port + ' ' + (@($profileEntry.server_args | ForEach-Object { '"' + [string]$_ + '"' }) -join ' ')),
            'exit /b %ERRORLEVEL%'
        )
        [IO.File]::WriteAllText($launcher, ($launcherLines -join "`r`n") + "`r`n", [Text.UTF8Encoding]::new($false))

        $serverArgs = @('--launcher', (Quote-Argument $launcher), '--state-dir', (Quote-Argument ([string]$script:supervisor.state_dir)),
            '--api-key-file', (Quote-Argument ([string]$registry.api_key_file)), '--token-file', (Quote-Argument ([string]$script:supervisor.token_file)),
            '--server-url', (Quote-Argument "http://127.0.0.1:$script:port"), '--console-log')
        if ($script:supervisor.sync_client_context -eq $true) { $serverArgs += '--sync-client-context' }
        $desktopConfig = [string](Get-Property $script:supervisor 'desktop_restart_config' '')
        if ($desktopConfig -and (Test-Path -LiteralPath $desktopConfig -PathType Leaf)) {
            $serverArgs += @('--desktop-restart-config', (Quote-Argument $desktopConfig))
        }
        $command = (Quote-Argument ([string]$script:supervisor.python)) + ' ' + (Quote-Argument ([string]$script:supervisor.script)) + ' ' + ($serverArgs -join ' ')

        Write-Progress-Line "stopping previous scenario: $name"
        Wait-ServerIdle $IdleTimeoutSeconds
        $previousLauncher = if ($script:activeScenario) { [string]$script:scenarioRoots[$script:activeScenario] } else { $script:oldLauncher }
        $script:scenarioRoots[$name] = $launcher
        $script:activeScenario = $name
        Stop-ManagedLauncher $previousLauncher
        $rootPid = Start-Manager $command ([string]$script:supervisor.working_directory)
        $allowedGpus = [int[]]$scenario.allowed
        Write-Progress-Line "starting scenario $name; allowed GPU set $($allowedGpus -join ',')"
        $ready = Wait-Ready $modelName $enginePath $allowedGpus ([int](Get-Property $profileEntry 'ready_timeout_seconds' 1800)) $rootPid $managedConfig $visionOn
        Invoke-TimedCompletion $WarmupTokens $true | Out-Null
        $samples = [System.Collections.Generic.List[object]]::new()
        for ($round = 1; $round -le $Rounds; $round++) {
            $result = Invoke-TimedCompletion $OutputTokens
            $samples.Add([pscustomobject]@{ round = $round; seconds = $result.seconds; completion_tokens = $result.completion_tokens; decode_tokens_per_second = $result.tokens_per_second; prompt_tokens = $result.prompt_tokens; prompt_tokens_per_second = $result.prompt_tokens_per_second; cached_prompt_tokens = $result.cached_prompt_tokens; wall_tokens_per_second = $result.wall_tokens_per_second })
            $rateText = '{0:N2}' -f $result.tokens_per_second
            if ($result.prompt_tokens -gt 1000) {
                $promptText = '{0:N1}' -f $result.prompt_tokens_per_second
                Write-Progress-Line "scenario $name round $round decode $rateText tok/s; prompt $($result.prompt_tokens) at $promptText tok/s (cached $($result.cached_prompt_tokens))"
            } else {
                Write-Progress-Line "scenario $name round $round $rateText tok/s"
            }
        }
        $sorted = @($samples | Sort-Object decode_tokens_per_second)
        $median = $sorted[[int][Math]::Floor(($sorted.Count - 1) / 2.0)].decode_tokens_per_second
        $imageSamples = @()
        if ($ImageRounds -gt 0) {
            Invoke-ImageProbe 1000 | Out-Null
            for ($ir = 1; $ir -le $ImageRounds; $ir++) {
                $probe = Invoke-ImageProbe (2000 + $ir)
                $imageSamples += [pscustomobject]@{ round = $ir; wall_seconds = $probe.wall_seconds; decode_tokens_per_second = $probe.decode_tokens_per_second; prompt_tokens = $probe.prompt_tokens; cached_prompt_tokens = $probe.cached_prompt_tokens; vision_gpu_rows = $probe.vision_gpu_rows }
                $wallText = '{0:N2}' -f $probe.wall_seconds
                Write-Progress-Line "scenario $name image round $ir wall ${wallText}s prompt $($probe.prompt_tokens) vision_on_gpu=$($probe.vision_gpu_rows.Count)"
            }
        }
        $finalPlacement = Assert-EnginePlacement $enginePath $allowedGpus $visionOn
        $gpuState = @(Get-GpuMap | Select-Object index, display, used_mib, free_mib)
        $scenarioResults.Add([pscustomobject]@{
            scenario = $name; requested_gpu = $scenarioGpu; argument_changes = $scenario.changes
            model = $modelName; context = $ready.health.max_context
            median_tokens_per_second = $median; samples = $samples; image_samples = $imageSamples; placement = $finalPlacement
            gpu_state_after = $gpuState; engine_log = $testConfig.log
        })
        [IO.File]::WriteAllText($jsonPath, (@($scenarioResults) | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    }

    Write-Progress-Line 'all scenarios finished; restoring previous server'
    Wait-ServerIdle $IdleTimeoutSeconds
    Stop-ManagedLauncher ([string]$script:scenarioRoots[$script:activeScenario])
    $script:activeScenario = $null
    $portOwners = @(Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue)
    $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
    $managers = @(Get-ManagerRoots)
    if ($portOwners.Count -or $engines.Count -or $managers.Count) {
        throw "refusing restore launch while processes remain: listeners=$($portOwners.Count), engines=$($engines.Count), supervisors=$($managers.Count)"
    }
    $restore = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $script:oldCommandLine; CurrentDirectory = $script:oldWorkingDirectory
    }
    if ($restore.ReturnValue -ne 0) { throw "could not restore previous supervisor (return $($restore.ReturnValue))" }
    $script:restoreManagerPid = [int]$restore.ProcessId
    $ready = Wait-Ready $script:oldModel $enginePath @(1) ([int](Get-Property $script:supervisor 'restore_timeout_seconds' 1800)) $script:restoreManagerPid
    $roots = @(Get-ManagerRoots)
    if ($roots.Count -ne 1) { throw "restored service has $($roots.Count) supervisor roots" }
    $script:restored = $true

    [IO.File]::WriteAllText($jsonPath, (@($scenarioResults) | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    $csvPath = Join-Path $ResultDirectory "gpu-settings-$startedAt.csv"
    @($scenarioResults | ForEach-Object {
        [pscustomobject]@{ scenario = $_.scenario; requested_gpu = $_.requested_gpu
            median_tokens_per_second = $_.median_tokens_per_second; context = $_.context
            argument_changes = ($_.argument_changes.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ' ' }
    }) | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
    Write-Host "RESULTS=$jsonPath"
    Write-Host "CSV=$csvPath"
}
finally {
    if (-not $script:restored -and $script:activeScenario) {
        $stopped = $false
        try {
            $health = Get-Health
            if ($health -and $health.loaded) { Wait-ServerIdle $IdleTimeoutSeconds }
            Stop-ManagedLauncher ([string]$script:scenarioRoots[$script:activeScenario])
            $stopped = $true
        } catch {
            Write-Progress-Line "scenario drain failed; refusing to start a second server: $($_.Exception.Message)"
        }
        if ($stopped) {
            $script:activeScenario = $null
            $portOwners = @(Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue)
            $engines = @(Get-CimInstance Win32_Process -Filter "Name='strata.exe'" -ErrorAction SilentlyContinue)
            $managers = @(Get-ManagerRoots)
            if (-not $portOwners.Count -and -not $engines.Count -and -not $managers.Count) {
                try {
                    $restore = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
                        CommandLine = $script:oldCommandLine; CurrentDirectory = $script:oldWorkingDirectory
                    }
                    if ($restore.ReturnValue -ne 0) { throw "previous supervisor restore failed (return $($restore.ReturnValue))" }
                    $script:restoreManagerPid = [int]$restore.ProcessId
                    $null = Wait-Ready $script:oldModel $enginePath @(1) ([int](Get-Property $script:supervisor 'restore_timeout_seconds' 1800)) $script:restoreManagerPid
                    $roots = @(Get-ManagerRoots)
                    if ($roots.Count -ne 1) { throw "restored service has $($roots.Count) supervisor roots" }
                    $script:restored = $true
                } catch {
                    Write-Progress-Line "previous server restoration did not verify: $($_.Exception.Message)"
                }
            } else {
                Write-Progress-Line "refusing restore launch: listeners=$($portOwners.Count), engines=$($engines.Count), supervisors=$($managers.Count)"
            }
        }
    } elseif (-not $script:restored -and $script:restoreManagerPid -and (Get-Process -Id $script:restoreManagerPid -ErrorAction SilentlyContinue)) {
        Write-Progress-Line "restore supervisor PID $script:restoreManagerPid is still active; not launching a duplicate"
    }
    Write-Host "RESTORED=$script:restored"
}
