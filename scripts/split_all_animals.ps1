# Batch-runs scripts/split_animal_asset.py via Blender on every Quaternius
# animal .gltf file. Outputs the 3 split .glb files per animal into
# static/{rigs,models,animations}/.
#
# Usage:
#   pwsh -File scripts/split_all_animals.ps1
#   pwsh -File scripts/split_all_animals.ps1 -SourceDir 'C:\path\to\glTF' -Blender 'C:\path\to\blender.exe'

param(
    [string]$SourceDir = 'C:\Users\lmwat\Downloads\glTF-extracted\glTF',
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 4.4\blender.exe'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SplitScript = Join-Path $PSScriptRoot 'split_animal_asset.py'

# Map of source-file stem -> slug used in output filenames.
# Slugs are lowercase and use no underscores so they read cleanly in the UI dropdown.
$Animals = [ordered]@{
    'Alpaca'      = 'alpaca'
    'Bull'        = 'bull'
    'Cow'         = 'cow'
    'Deer'        = 'deer'
    'Donkey'      = 'donkey'
    'Fox'         = 'foxq'           # 'foxq' to avoid clash with existing fox
    'Horse'       = 'horseq'         # 'horseq' to avoid clash with existing horse work
    'Horse_White' = 'horsewhite'
    'Husky'       = 'husky'
    'ShibaInu'    = 'shibainu'
    'Stag'        = 'stag'
}

if (-not (Test-Path $Blender)) {
    Write-Error "Blender not found at: $Blender"
    exit 1
}
if (-not (Test-Path $SourceDir)) {
    Write-Error "Source dir not found: $SourceDir"
    exit 1
}
if (-not (Test-Path $SplitScript)) {
    Write-Error "Splitter script not found: $SplitScript"
    exit 1
}

$failures = @()
$successes = @()

foreach ($entry in $Animals.GetEnumerator()) {
    $stem = $entry.Key
    $slug = $entry.Value
    $input = Join-Path $SourceDir "$stem.gltf"

    if (-not (Test-Path $input)) {
        Write-Warning "Skipping $stem - source not found at $input"
        $failures += $stem
        continue
    }

    Write-Host ""
    Write-Host "================================================================"
    Write-Host "Processing: $stem (slug='$slug')"
    Write-Host "================================================================"

    # Do NOT redirect 2>&1 -- in Windows PowerShell 5.1 that wraps native stderr in
    # ErrorRecord which corrupts $LASTEXITCODE. Blender prints handler warnings to
    # stderr on every run; those are not failures. The real test is whether the
    # three expected output files exist and are non-trivially sized.
    & $Blender --background --python $SplitScript -- --input $input --slug $slug --project-root $ProjectRoot |
        Where-Object { $_ -match "^\[$slug\]|ERROR" }

    $expected = @(
        Join-Path $ProjectRoot "static\rigs\rig-$slug.glb"
        Join-Path $ProjectRoot "static\models\model-$slug.glb"
        Join-Path $ProjectRoot "static\animations\$slug-animations.glb"
    )
    $allExist = $expected | ForEach-Object { (Test-Path $_) -and (Get-Item $_).Length -gt 1024 } | Where-Object { -not $_ }
    if ($allExist.Count -gt 0) {
        Write-Warning "Expected outputs missing or empty for $stem"
        $failures += $stem
    }
    else {
        $successes += $stem
    }
}

Write-Host ""
Write-Host "================================================================"
Write-Host "SUMMARY"
Write-Host "================================================================"
Write-Host ("Success ({0}): {1}" -f $successes.Count, ($successes -join ', '))
if ($failures.Count -gt 0) {
    Write-Host ("Failed ({0}): {1}" -f $failures.Count, ($failures -join ', '))
    exit 1
}
