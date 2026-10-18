#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$allowRuleName = 'StrataOpenCodeLan8080'
$blockRuleName = 'StrataOpenCodeNotPrivate8080'

function Test-Is8080TcpRule($Rule) {
    $filters = @($Rule | Get-NetFirewallPortFilter -ErrorAction Stop)
    foreach ($filter in $filters) {
        if ([string]$filter.Protocol -notin @('TCP', '6', 'Any', '256')) { continue }
        foreach ($value in @($filter.LocalPort)) {
            $port = [string]$value
            if ($port -eq 'Any' -or $port -eq '8080') { return $true }
            if ($port -match '^(\d+)-(\d+)$' -and [int]$Matches[1] -le 8080 -and [int]$Matches[2] -ge 8080) {
                return $true
            }
        }
    }
    return $false
}

$activeProfiles = @(Get-NetConnectionProfile -ErrorAction Stop |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' })
if (-not $activeProfiles -or ($activeProfiles | Where-Object NetworkCategory -ne 'Private')) {
    throw 'Strata LAN startup requires at least one active Private network and no active Domain/Public network.'
}

$firewallProfiles = @(Get-NetFirewallProfile -ErrorAction Stop)
if ($firewallProfiles | Where-Object { -not $_.Enabled }) {
    throw 'Windows Firewall must be enabled for all profiles.'
}

$allowRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $allowRuleName -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' })
if ($allowRules.Count -ne 1 -or -not (Test-Is8080TcpRule $allowRules[0])) {
    throw 'The Private/LocalSubnet TCP 8080 allow rule is missing. Run allow_strata_lan.ps1 from elevated PowerShell first.'
}
$allowProfiles = @($allowRules[0].Profile | ForEach-Object { "$($_)".Split(',') })
$allowRemote = @($allowRules[0] | Get-NetFirewallAddressFilter | ForEach-Object { $_.RemoteAddress } | ForEach-Object { "$($_)".Split(',') })
if ($allowProfiles.Count -ne 1 -or $allowProfiles[0] -ne 'Private' -or
    $allowRemote.Count -ne 1 -or $allowRemote[0] -ne 'LocalSubnet') {
    throw 'The Strata allow rule is broader than Private/LocalSubnet. No server was started.'
}

$blockRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $blockRuleName -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' })
if ($blockRules.Count -ne 1 -or -not (Test-Is8080TcpRule $blockRules[0])) {
    throw 'The Domain/Public TCP 8080 block rule is missing. Run allow_strata_lan.ps1 from elevated PowerShell first.'
}
$blockProfiles = @($blockRules[0].Profile | ForEach-Object { "$($_)".Split(',') })
if (-not ($blockProfiles -contains 'Domain') -or -not ($blockProfiles -contains 'Public')) {
    throw 'The Strata TCP 8080 block rule must cover both Domain and Public profiles.'
}

$setupRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$serverPythonPaths = @(
    [System.IO.Path]::GetFullPath((Join-Path $setupRoot '.venv\Scripts\python.exe')),
    [System.IO.Path]::GetFullPath((Join-Path (Join-Path $env:USERPROFILE 'Strata') '.venv\Scripts\python.exe'))
)
$enabledAllows = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Action Allow -Enabled True)
foreach ($candidate in $enabledAllows) {
    $profileNames = @($candidate.Profile | ForEach-Object { "$($_)".Split(',') })
    if (-not ($profileNames -contains 'Any' -or $profileNames -contains 'Private')) { continue }
    if (-not (Test-Is8080TcpRule $candidate)) { continue }

    $applicationFilter = $candidate | Get-NetFirewallApplicationFilter
    $program = [Environment]::ExpandEnvironmentVariables([string]$applicationFilter.Program).Trim('"')
    if ($program -and $program -notin @('Any', '*')) {
        try { $program = [System.IO.Path]::GetFullPath($program) } catch { continue }
        if (-not ($serverPythonPaths | Where-Object { [string]::Equals($_, $program, [StringComparison]::OrdinalIgnoreCase) })) {
            continue
        }
    }
    $serviceFilter = $candidate | Get-NetFirewallServiceFilter
    $service = [string]$serviceFilter.Service
    if ($service -and $service -notin @('Any', '*')) { continue }

    $remote = @($candidate | Get-NetFirewallAddressFilter | ForEach-Object { $_.RemoteAddress } | ForEach-Object { "$($_)".Split(',') })
    if (-not $remote -or $remote -contains 'Any' -or $remote -contains '*') {
        throw "Inbound rule '$($candidate.DisplayName)' can expose Strata TCP 8080 beyond a scoped peer list. Run allow_strata_lan.ps1 or review the rule. No server was started."
    }
    foreach ($address in $remote) {
        if ($address -eq 'LocalSubnet') { continue }
        if ($address -notmatch '^(\d{1,3}\.){3}\d{1,3}$' -and $address -notmatch '^[0-9a-fA-F:]+$') {
            throw "Inbound rule '$($candidate.DisplayName)' has an unverified remote scope '$address'. No server was started."
        }
    }
}

Write-Output 'PASS: active networks are Private; TCP 8080 is limited to Private/LocalSubnet and blocked on Domain/Public.'
