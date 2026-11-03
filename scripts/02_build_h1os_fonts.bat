@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "REPO_ROOT=%CD%"
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PY_BIN=%REPO_ROOT%\.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PY_BIN=python"
    ) else (
        set "PY_BIN=py -3"
    )
)
echo ============================================================================
echo [epd-font v0.0.6] Step 2: Building H1OS 1-BPP C/H Fonts, BDFs ^& Strike Vault
echo ============================================================================
"%PY_BIN%" tools\fonts\generate_plex_1bpp.py --workflow build --scheme tools\fonts\schemes\h1os_epd_scheme.json --src-dir assets\static_ttfs --out-dir build --audit-screens
if exist "build\dist\plex_epd_vault.json.gz" (
    if not exist "dist" mkdir dist
    copy /Y "build\dist\plex_epd_vault.json.gz" "dist\plex_epd_vault.json.gz" >nul
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Script failed with exit code %ERRORLEVEL%.
    if "%CI%"=="" if "%1" NEQ "--no-pause" pause
    exit /b %ERRORLEVEL%
)
echo.
echo [+] Completed successfully.
if "%CI%"=="" if "%1" NEQ "--no-pause" pause
exit /b 0
