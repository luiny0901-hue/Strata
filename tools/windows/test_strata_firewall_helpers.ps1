#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$script:TestTailscaleAddresses = @(
    [pscustomobject]@{ InterfaceAlias = 'Tailscale'; AddressState = 'Preferred'; IPAddress = '100.64.0.10' },
    [pscustomobject]@{ InterfaceAlias = 'Tailscale'; AddressState = 'Preferred'; IPAddress = 'fd7a:115c:a1e0::10' }
)

function Get-NetFirewallAddressFilter {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $InputObject.TestAddressFilter }
}

function Get-NetFirewallPortFilter {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)]$InputObject)
    process { $InputObject.TestPortFilter }
}

function Get-NetIPAddress {
    [CmdletBinding()]
    param()
    $script:TestTailscaleAddresses
}

. (Join-Path $PSScriptRoot 'strata_firewall_helpers.ps1')

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)
    if ($Actual -ne $Expected) { throw "$Name expected '$Expected', received '$Actual'." }
    Write-Output "PASS: $Name"
}

function New-TestRule {
    param([string]$LocalAddress, [string]$Profile = 'Domain, Private', [string]$DisplayName = 'Tailscale-In')
    [pscustomobject]@{
        Name = 'TestRule'
        DisplayName = $DisplayName
        Direction = 'Inbound'
        Action = 'Allow'
        Enabled = $true
        Profile = $Profile
        TestAddressFilter = [pscustomobject]@{ LocalAddress = $LocalAddress; RemoteAddress = 'Any' }
        TestPortFilter = [pscustomobject]@{ Protocol = 'Any'; LocalPort = 'Any' }
    }
}

Assert-Equal -Actual (@(ConvertTo-StrataFirewallValue -Values @('Domain, Public')).Count) -Expected 2 -Name 'profile values are split and trimmed'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress '100.64.0.10')) -Expected $true -Name 'current IPv4 Tailscale address is accepted'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress 'fd7a:115c:a1e0::10')) -Expected $true -Name 'current IPv6 Tailscale address is accepted'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress 'Any')) -Expected $false -Name 'unscoped local address is rejected'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress '100.64.0.11')) -Expected $false -Name 'stale Tailscale address is rejected'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress '100.64.0.10' -Profile 'Private, Public')) -Expected $false -Name 'Public profile is rejected'
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule (New-TestRule -LocalAddress '100.64.0.10' -DisplayName 'Unrelated Rule')) -Expected $false -Name 'unrelated rule name is rejected'

Assert-Equal -Actual (Test-StrataFirewallRuleIncludesTcp8080 -Rule (New-TestRule -LocalAddress '100.64.0.10')) -Expected $true -Name 'Any protocol and port include TCP 8080'
$tcp22 = New-TestRule -LocalAddress '100.64.0.10'
$tcp22.TestPortFilter = [pscustomobject]@{ Protocol = 'TCP'; LocalPort = '22' }
Assert-Equal -Actual (Test-StrataFirewallRuleIncludesTcp8080 -Rule $tcp22) -Expected $false -Name 'unrelated TCP port is ignored'
$udp8080 = New-TestRule -LocalAddress '100.64.0.10'
$udp8080.TestPortFilter = [pscustomobject]@{ Protocol = 'UDP'; LocalPort = '8080' }
Assert-Equal -Actual (Test-StrataFirewallRuleIncludesTcp8080 -Rule $udp8080) -Expected $false -Name 'UDP 8080 is not treated as TCP 8080'
$tailscale22 = New-TestRule -LocalAddress '100.64.0.10'
$tailscale22.TestPortFilter = [pscustomobject]@{ Protocol = 'TCP'; LocalPort = '22' }
Assert-Equal -Actual (Test-StrataTailscaleScopedAllowRule -Rule $tailscale22) -Expected $false -Name 'Tailscale rule without TCP 8080 is not accepted as a Strata path'

Write-Output 'PASS: all firewall helper checks passed.'
