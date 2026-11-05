param(
    [ValidateRange(0, 60)][double]$GapSeconds = 1,
    [switch]$Mute
)
$ErrorActionPreference = 'Stop'
$simulationRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$simulationPython = Join-Path $simulationRoot 'platform\api\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $simulationPython)) {
    throw 'The platform Python environment is missing. Follow start/README.md.'
}
$simulationArguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'launch_test.py'), '--gap-seconds', $GapSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture))
if ($Mute) { $simulationArguments += '--mute' }
& $simulationPython @simulationArguments
exit $LASTEXITCODE
