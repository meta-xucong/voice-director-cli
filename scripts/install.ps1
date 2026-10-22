[CmdletBinding()]
param(
    [string]$SkillsRoot
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $SkillsRoot) {
    if ($env:CODEX_HOME) {
        $SkillsRoot = Join-Path $env:CODEX_HOME 'skills'
    } else {
        $SkillsRoot = Join-Path $env:USERPROFILE '.codex\skills'
    }
}

function Get-Python312 {
    $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $pythonPath = (& $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $pythonPath -and (Test-Path -LiteralPath $pythonPath)) {
                return $pythonPath.Trim()
            }
        } catch {
            # Continue through known installation locations.
        }
    }

    $candidates = @()
    if ($env:LocalAppData) {
        $candidates += Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'
    }
    $candidates += 'C:\Program Files\Python312\python.exe'
    $pythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        try {
            & $candidate -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {
            # Ignore invalid aliases or incompatible Python installations.
        }
    }

    return $null
}

function Test-SameTree([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { return $false }

    $sourceFiles = @(Get-ChildItem -LiteralPath $Source -File -Recurse | ForEach-Object {
        [PSCustomObject]@{
            Relative = $_.FullName.Substring($Source.Length).TrimStart('\', '/')
            Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    } | Sort-Object Relative)
    $destinationFiles = @(Get-ChildItem -LiteralPath $Destination -File -Recurse | ForEach-Object {
        [PSCustomObject]@{
            Relative = $_.FullName.Substring($Destination.Length).TrimStart('\', '/')
            Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    } | Sort-Object Relative)

    if ($sourceFiles.Count -ne $destinationFiles.Count) { return $false }
    for ($index = 0; $index -lt $sourceFiles.Count; $index++) {
        if ($sourceFiles[$index].Relative -ne $destinationFiles[$index].Relative -or
            $sourceFiles[$index].Hash -ne $destinationFiles[$index].Hash) {
            return $false
        }
    }
    return $true
}

$skillNames = @(
    'courseware-pipeline-bootstrap',
    'courseware-pipeline',
    'source-to-script',
    'humanized-source-rewrite'
)

# Validate every source and destination before installing Python or copying any Skill.
foreach ($name in $skillNames) {
    $source = Join-Path $repoRoot "skills\$name"
    $destination = Join-Path $SkillsRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Repository is missing the expected Skill folder: $source"
    }
    if ((Test-Path -LiteralPath $destination) -and
        -not (Test-SameTree -Source $source -Destination $destination)) {
        throw "A different Skill already exists at '$destination'. No files were overwritten; inspect or move it, then rerun."
    }
}

$python = Get-Python312
if (-not $python) {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Python 3.12 was not found and WinGet is unavailable. Install Python 3.12, then rerun this script.'
    }

    Write-Host 'Python 3.12 is missing. Installing it with WinGet (Python.Python.3.12)...'
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet could not install Python 3.12 (exit $LASTEXITCODE). Install Python 3.12 and rerun this script."
    }
    $python = Get-Python312
    if (-not $python) {
        throw 'Python 3.12 installation completed, but this shell cannot locate it yet. Open a new terminal and rerun this script.'
    }
}

$version = & $python --version
Write-Host "Using $version at $python"

Push-Location $repoRoot
try {
    Write-Host 'Checking CLI entry point...'
    & $python -m voice_director --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Voice Director CLI help check failed.' }

    Write-Host 'Running offline tests...'
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Offline tests failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Path $SkillsRoot -Force | Out-Null
foreach ($name in $skillNames) {
    $source = Join-Path $repoRoot "skills\$name"
    $destination = Join-Path $SkillsRoot $name
    if (Test-Path -LiteralPath $destination) {
        Write-Host "Already current: $name"
        continue
    }
    Copy-Item -LiteralPath $source -Destination $SkillsRoot -Recurse
    Write-Host "Installed: $name"
}

Write-Host "Setup complete. Repository: $repoRoot"
Write-Host "Codex Skills: $SkillsRoot"
Write-Host 'Refresh or restart Codex if the new Skills are not visible yet.'
