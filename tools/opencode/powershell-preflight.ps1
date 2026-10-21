function Get-OpenCodeCommandPreflight([string]$Source) {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Source, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) { return 2 }
    $elevation = $ast.FindAll({ param($node)
        if ($node -isnot [System.Management.Automation.Language.CommandAst]) { return $false }
        $name = $node.GetCommandName()
        if (-not $name) { return $false }
        $leaf = [System.IO.Path]::GetFileNameWithoutExtension($name).ToLowerInvariant()
        if ($leaf -in @('runas', 'sudo', 'gsudo')) { return $true }
        if ($leaf -notin @('start-process', 'saps', 'start')) { return $false }
        $elements = $node.CommandElements
        for ($i = 1; $i -lt $elements.Count; $i++) {
            $element = $elements[$i]
            if ($element -is [System.Management.Automation.Language.CommandParameterAst] -and $element.ParameterName -match '^(?i:v|ve|ver|verb)$') {
                $value = $element.Argument
                if (-not $value -and $i + 1 -lt $elements.Count) { $value = $elements[$i + 1] }
                if ($value -isnot [System.Management.Automation.Language.StringConstantExpressionAst] -or $value.Value -ieq 'RunAs') { return $true }
            }
        }
        return $false
    }, $true)
    if ($elevation.Count -gt 0) { return 77 }
    return 0
}
