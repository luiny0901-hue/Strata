param(
    [string]$StrataRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$relativePath = 'forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4\serve\server.py'
$serverPath = Join-Path $StrataRoot $relativePath
$expectedBefore = 'A9D6BD95557EAE37F36D7F452463CE08451561887A5F85802A8E58DB90029D58'
$expectedAfter = '647F3AFF8DE6197523395AC8177DD2AEFB4105EBFA5BC457C0F6053446019543'

if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) {
    throw "NVFP4 server.py was not found at '$serverPath'. Extract fork 0.1.44.1-nvfp4.2 first."
}

$currentHash = (Get-FileHash -LiteralPath $serverPath -Algorithm SHA256).Hash
if ($currentHash -eq $expectedAfter) {
    Write-Output 'Vision pipe shutdown fix is already applied.'
    return
}
if ($currentHash -ne $expectedBefore) {
    throw "Unexpected NVFP4 server.py SHA-256 '$currentHash'. Refusing to modify an unreviewed fork version."
}

$newline = "`r`n"
$oldLines = @(
    '        self.stopped = True'
    ''
    '    def shutdown(self):'
)
$newLines = @(
    '        finally:'
    '            # Close the child pipe wrappers explicitly after wait/kill so TextIOWrapper finalization cannot'
    '            # flush to an already-exited vision encoder during Python shutdown.'
    '            for stream in (proc.stdin, proc.stdout):'
    '                if stream is not None:'
    '                    try:'
    '                        stream.close()'
    '                    except (OSError, ValueError):'
    '                        pass'
    '            self.stopped = True'
    ''
    '    def shutdown(self):'
)
$oldText = $oldLines -join $newline
$newText = $newLines -join $newline
$source = [System.IO.File]::ReadAllText($serverPath)
$insertionMatches = [regex]::Matches($source, [regex]::Escape($oldText))
if ($insertionMatches.Count -ne 1) {
    throw "Expected exactly one Vision.close() insertion point; found $($insertionMatches.Count). No file was changed."
}

$updated = $source.Replace($oldText, $newText)
[System.IO.File]::WriteAllText($serverPath, $updated, [System.Text.UTF8Encoding]::new($false))
$resultHash = (Get-FileHash -LiteralPath $serverPath -Algorithm SHA256).Hash
if ($resultHash -ne $expectedAfter) {
    throw "Post-patch SHA-256 '$resultHash' did not match the reviewed result. Inspect the file and do not launch it."
}

Write-Output "Applied NVFP4 vision pipe cleanup. SHA-256: $resultHash"
