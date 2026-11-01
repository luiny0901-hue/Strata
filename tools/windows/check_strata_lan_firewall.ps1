#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$helperPath = Join-Path $PSScriptRoot 'strata_firewall_helpers.ps1'
. $helperPath
$allowRuleName = 'StrataOpenCodeLan8080'
$blockRuleName = 'StrataOpenCodeNotPrivate8080'

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
if ($allowRules.Count -ne 1 -or -not (Test-StrataFirewallRuleIncludesTcp8080 -Rule $allowRules[0])) {
    throw 'The Private/LocalSubnet TCP 8080 allow rule is missing. Run allow_strata_lan.ps1 from elevated PowerShell first.'
}
$allowProfiles = @(ConvertTo-StrataFirewallValue -Values @($allowRules[0].Profile))
$allowRemote = @(ConvertTo-StrataFirewallValue -Values @($allowRules[0] | Get-NetFirewallAddressFilter | ForEach-Object { $_.RemoteAddress }))
if ($allowProfiles.Count -ne 1 -or $allowProfiles[0] -ne 'Private' -or
    $allowRemote.Count -ne 1 -or $allowRemote[0] -ne 'LocalSubnet') {
    throw 'The Strata allow rule is broader than Private/LocalSubnet. No server was started.'
}

$blockRules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $blockRuleName -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' })
if ($blockRules.Count -ne 1 -or -not (Test-StrataFirewallRuleIncludesTcp8080 -Rule $blockRules[0])) {
    throw 'The Domain/Public TCP 8080 block rule is missing. Run allow_strata_lan.ps1 from elevated PowerShell first.'
}
$blockProfiles = @(ConvertTo-StrataFirewallValue -Values @($blockRules[0].Profile))
if (-not ($blockProfiles -contains 'Domain') -or -not ($blockProfiles -contains 'Public')) {
    throw 'The Strata TCP 8080 block rule must cover both Domain and Public profiles.'
}

$setupRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$serverPythonPaths = @(
    [System.IO.Path]::GetFullPath((Join-Path $setupRoot '.venv\Scripts\python.exe')),
    [System.IO.Path]::GetFullPath((Join-Path (Join-Path $env:USERPROFILE 'Strata') '.venv\Scripts\python.exe'))
)
$enabledAllows = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Action Allow -Enabled True)
$tailscaleRuleCount = 0
foreach ($candidate in $enabledAllows) {
    if (Test-StrataTailscaleScopedAllowRule -Rule $candidate) {
        $tailscaleRuleCount++
        continue
    }

    $profileNames = @(ConvertTo-StrataFirewallValue -Values @($candidate.Profile))
    if (-not ($profileNames -contains 'Any' -or $profileNames -contains 'Private')) { continue }

    # This rule is scoped to a packaged Windows app, not the venv Python Strata server.
    if ($candidate.PackageFamilyName) { continue }
    if (-not (Test-StrataFirewallRuleIncludesTcp8080 -Rule $candidate)) { continue }

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

    $remote = @(ConvertTo-StrataFirewallValue -Values @($candidate | Get-NetFirewallAddressFilter | ForEach-Object { $_.RemoteAddress }))
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

if ($tailscaleRuleCount -gt 0) {
    Write-Output "Tailscale: accepted $tailscaleRuleCount existing Tailscale-In rule(s) bound to current Tailscale interface address(es); they may permit broader inbound traffic than Strata TCP 8080, so review Tailscale peer ACLs."
}
Write-Output 'PASS: LAN access is limited to Private/LocalSubnet, Domain/Public are blocked, and only current Tailscale interface addresses use the existing Tailscale-In path.'
