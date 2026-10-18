#Requires -RunAsAdministrator
#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$helperPath = Join-Path $PSScriptRoot 'strata_firewall_helpers.ps1'
. $helperPath
$allowRuleName = 'StrataOpenCodeLan8080'
$blockRuleName = 'StrataOpenCodeNotPrivate8080'
$displayName = 'Strata OpenCode API - Private LAN only'

$activeProfiles = @(Get-NetConnectionProfile -ErrorAction Stop |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' })
if (-not $activeProfiles -or -not ($activeProfiles | Where-Object NetworkCategory -eq 'Private')) {
    throw 'Set at least one active Windows network to Private before enabling LAN access.'
}

$firewallProfiles = @(Get-NetFirewallProfile -ErrorAction Stop)
if ($firewallProfiles | Where-Object { -not $_.Enabled }) {
    throw 'Windows Firewall must be enabled for every profile before enabling LAN access.'
}

# A broad pre-existing allow rule would defeat a LocalSubnet-only rule. Refuse
# to proceed rather than silently widening or deleting a rule owned elsewhere.
$setupRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$serverPythonPaths = @(
    [System.IO.Path]::GetFullPath((Join-Path $setupRoot '.venv\Scripts\python.exe')),
    [System.IO.Path]::GetFullPath((Join-Path (Join-Path $env:USERPROFILE 'Strata') '.venv\Scripts\python.exe'))
)
$legacyRulesToRestrict = @()
$tailscaleRuleCount = 0
$enabledAllows = @(Get-NetFirewallRule -PolicyStore ActiveStore -Direction Inbound -Action Allow -Enabled True)
foreach ($candidate in $enabledAllows) {
    if ($candidate.Name -eq $allowRuleName) { continue }
    if (Test-StrataTailscaleScopedAllowRule -Rule $candidate) {
        $tailscaleRuleCount++
        continue
    }

    $profileNames = @(ConvertTo-StrataFirewallValue -Values @($candidate.Profile))
    if (-not ($profileNames -contains 'Any' -or $profileNames -contains 'Private')) { continue }

    # This rule is scoped to a packaged Windows app, not the venv Python Strata server.
    if ($candidate.PackageFamilyName) { continue }

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

    $ports = @($candidate | Get-NetFirewallPortFilter)
    if (-not (Test-StrataFirewallRuleIncludesTcp8080 -Rule $candidate)) { continue }

    $remoteAddresses = @($candidate | Get-NetFirewallAddressFilter | ForEach-Object { $_.RemoteAddress })
    $remoteValues = @(ConvertTo-StrataFirewallValue -Values $remoteAddresses)
    if (-not $remoteValues -or $remoteValues -contains 'Any' -or $remoteValues -contains '*') {
        $exactLegacyPort = $ports.Count -eq 1 -and
            $ports[0].Protocol -eq 'TCP' -and
            @($ports[0].LocalPort).Count -eq 1 -and
            [string]$ports[0].LocalPort -eq '8080'
        $isExactLegacyRule = $exactLegacyPort -and
            $program -eq 'Any' -and
            $service -eq 'Any' -and
            $remoteValues.Count -eq 1 -and
            $remoteValues[0] -eq 'Any'
        $isKnownLegacyRule = $isExactLegacyRule -and (
            ($candidate.DisplayName -eq 'llama-server-8080' -and $profileNames.Count -eq 1 -and $profileNames[0] -eq 'Any') -or
            ($candidate.DisplayName -eq 'llama.cpp API 8080 LAN' -and $profileNames.Count -eq 1 -and $profileNames[0] -eq 'Private')
        )
        if ($isKnownLegacyRule) {
            $legacyRulesToRestrict += $candidate
            continue
        }
        throw "Enabled inbound rule '$($candidate.DisplayName)' may allow TCP 8080 beyond LocalSubnet. Review that rule before enabling LAN access. No firewall rules were changed."
    }

    foreach ($remoteValue in $remoteValues) {
        if ($remoteValue -in @('LocalSubnet', 'LocalSubnet4', 'LocalSubnet6')) { continue }
        if ($remoteValue -match '^(\d{1,3}\.){3}\d{1,3}$' -or $remoteValue -match '^[0-9a-fA-F:]+$') { continue }
        throw "Enabled inbound rule '$($candidate.DisplayName)' has an unverified remote scope '$remoteValue'. Review that rule before enabling LAN access. No firewall rules were changed."
    }
}

$blockRule = Get-NetFirewallRule -Name $blockRuleName -ErrorAction SilentlyContinue
if ($blockRule) {
    Set-NetFirewallRule -Name $blockRuleName -NewDisplayName 'Strata OpenCode API - Block Domain and Public networks' `
        -Description 'Prevents Strata API access on Domain/Public network profiles.' -Direction Inbound -Action Block `
        -Enabled True -Profile Domain,Public -Protocol TCP -LocalPort 8080 -RemoteAddress Any -EdgeTraversalPolicy Block
    $blockRule = Get-NetFirewallRule -Name $blockRuleName
} else {
    $blockRule = New-NetFirewallRule `
        -Name $blockRuleName `
        -DisplayName 'Strata OpenCode API - Block Domain and Public networks' `
        -Description 'Prevents Strata API access on Domain/Public network profiles.' `
        -Direction Inbound `
        -Action Block `
        -Enabled True `
        -Profile Domain,Public `
        -Protocol TCP `
        -LocalPort 8080 `
        -RemoteAddress Any `
        -EdgeTraversalPolicy Block
}

foreach ($legacyRule in $legacyRulesToRestrict) {
    Set-NetFirewallRule -PolicyStore PersistentStore -Name $legacyRule.Name `
        -Profile Private -RemoteAddress LocalSubnet -ErrorAction Stop
    Write-Output "Restricted existing rule '$($legacyRule.DisplayName)' to Private/LocalSubnet."
}

$allowRule = Get-NetFirewallRule -Name $allowRuleName -ErrorAction SilentlyContinue
if ($allowRule) {
    Set-NetFirewallRule -Name $allowRuleName -NewDisplayName $displayName `
        -Description 'Allows authenticated Strata API access only from directly connected local subnets on Private networks.' `
        -Direction Inbound -Action Allow -Enabled True -Profile Private -Protocol TCP -LocalPort 8080 `
        -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block
    $allowRule = Get-NetFirewallRule -Name $allowRuleName
} else {
    $allowRule = New-NetFirewallRule `
        -Name $allowRuleName `
        -DisplayName $displayName `
        -Description 'Allows authenticated Strata API access only from directly connected local subnets on Private networks.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Private `
        -Protocol TCP `
        -LocalPort 8080 `
        -RemoteAddress LocalSubnet `
        -EdgeTraversalPolicy Block
}

Write-Output "Applied firewall rule: $($allowRule.DisplayName)"
Write-Output "Applied firewall rule: $($blockRule.DisplayName)"
Write-Output 'LAN allow: TCP 8080, Private profile, RemoteAddress=LocalSubnet. Block: Domain/Public profiles.'
if ($tailscaleRuleCount -gt 0) {
    Write-Output "Tailscale: preserved $tailscaleRuleCount existing Tailscale-In rule(s) bound to current Tailscale interface address(es); they may permit broader inbound traffic than Strata TCP 8080, so review Tailscale peer ACLs."
} else {
    Write-Output 'Tailscale: no matching existing Tailscale-In path was found; only LAN access is configured by this script.'
}
