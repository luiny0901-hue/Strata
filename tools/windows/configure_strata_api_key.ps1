#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Generate')]
    [switch]$Generate,

    [Parameter(Mandatory = $true, ParameterSetName = 'Prompt')]
    [switch]$Prompt
)

$ErrorActionPreference = 'Stop'
$directory = Join-Path $env:USERPROFILE '.config\strata'
$path = Join-Path $directory 'STRATA_API_KEY'
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$adminSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$systemSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')

function Set-PrivateAcl([string]$Target, [bool]$IsDirectory) {
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    $inherit = if ($IsDirectory) { '(OI)(CI)' } else { '' }
    $principals = @(
        "*$($currentSid.Value):${inherit}F",
        "*$($adminSid.Value):${inherit}F",
        "*$($systemSid.Value):${inherit}F"
    )

    function Invoke-Icacls([string[]]$Arguments) {
        $null = & $icacls @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Could not set a private ACL on $Target (icacls exit $LASTEXITCODE)." }
    }

    Invoke-Icacls @($Target, '/reset')
    Invoke-Icacls @($Target, '/inheritance:r')
    foreach ($principal in $principals) {
        Invoke-Icacls @($Target, '/grant:r', $principal)
    }
}

New-Item -ItemType Directory -Path $directory -Force | Out-Null
Set-PrivateAcl $directory $true

if ($Generate) {
    if (Test-Path -LiteralPath $path) {
        $key = [System.IO.File]::ReadAllText($path).Trim()
        if ($key -cnotmatch '^[0-9a-fA-F]{64}$') {
            throw "Existing key file is invalid; it was not replaced: $path"
        }
        $result = 'Reused the existing key file.'
    } else {
        $bytes = [byte[]]::new(32)
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $key = [System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        [System.IO.File]::WriteAllText($path, $key, [System.Text.Encoding]::ASCII)
        $result = 'Created a new key file.'
    }
} else {
    $secureKey = Read-Host 'Paste the Strata API key (input hidden)' -AsSecureString
    $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $key = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($key -cnotmatch '^[0-9a-fA-F]{64}$') {
        throw 'The API key must be exactly 64 hexadecimal characters.'
    }
    [System.IO.File]::WriteAllText($path, $key, [System.Text.Encoding]::ASCII)
    $result = 'Saved the supplied key.'
}

Set-PrivateAcl $path $false
$key = $null
$secureKey = $null
Write-Output $result
Write-Output "Key file: $path"
Write-Output 'The key value was not displayed.'
