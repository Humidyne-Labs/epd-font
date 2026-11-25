$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $RepoRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv is required to provision the Python 3.12 .venv."
        exit 2
    }
    uv venv .venv --python 3.12
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    uv pip install --python $VenvPy -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $VenvPy --version
    Write-Host "[+] .venv provisioned successfully at $RepoRoot\.venv"
} finally {
    Pop-Location
}
