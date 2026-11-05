param([switch]$Worker,[switch]$Retention)
$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
if ($Retention) { uv run pms-worker --retention }
elseif ($Worker) { uv run pms-worker }
else { uv run pms-api }
exit $LASTEXITCODE
