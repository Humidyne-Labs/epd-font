$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Error "Missing .venv Python 3.12 environment at '$VenvPy'. Run scripts\setup_venv.ps1 first."
    exit 2
}
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUNBUFFERED = "1"
& $VenvPy (Join-Path $RepoRoot "runner\epd_font_cli.py") @args
exit $LASTEXITCODE
