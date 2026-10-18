#Requires -Version 5.1

function ConvertTo-StrataFirewallValue {
    param([object[]]$Values)

    foreach ($value in $Values) {
        if ($null -eq $value) { continue }
        foreach ($part in ([string]$value).Split(',')) {
            $normalized = $part.Trim()
            if ($normalized) { $normalized }
        }
    }
}

function Test-StrataFirewallRuleIncludesTcp8080 {
    param($Rule)

    foreach ($filter in @($Rule | Get-NetFirewallPortFilter -ErrorAction Stop)) {
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

function Test-StrataTailscaleScopedAllowRule {
    param($Rule)

    # Tailscale owns these broad inbound rules. Accept them only when they target
    # an exact address currently assigned to the Tailscale adapter; never rewrite them here.
    if ([string]$Rule.DisplayName -ne 'Tailscale-In' -or
        [string]$Rule.Direction -ne 'Inbound' -or
        [string]$Rule.Action -ne 'Allow' -or
        [string]$Rule.Enabled -ne 'True' -or
        -not (Test-StrataFirewallRuleIncludesTcp8080 -Rule $Rule)) {
        return $false
    }

    $profiles = @(ConvertTo-StrataFirewallValue -Values @($Rule.Profile))
    if ($profiles -notcontains 'Private' -or $profiles -contains 'Public') { return $false }

    $addressFilters = @($Rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
    $localAddresses = @(ConvertTo-StrataFirewallValue -Values @($addressFilters | ForEach-Object { $_.LocalAddress }))
    if (-not $localAddresses -or $localAddresses -contains 'Any' -or $localAddresses -contains '*') { return $false }

    $tailscaleAddresses = @(Get-NetIPAddress -ErrorAction Stop |
        Where-Object { $_.InterfaceAlias -like '*Tailscale*' -and $_.AddressState -eq 'Preferred' } |
        Select-Object -ExpandProperty IPAddress -Unique)
    if (-not $tailscaleAddresses) { return $false }

    foreach ($localAddress in $localAddresses) {
        if ($tailscaleAddresses -notcontains $localAddress) { return $false }
    }

    return $true
}
