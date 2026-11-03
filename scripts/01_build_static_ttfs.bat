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
echo [epd-font v0.0.6] Step 1: Converting Raw Assets -^> Static TTFs ^& JSON Catalogs
echo ============================================================================
"%PY_BIN%" tools\fonts\build_static_ttf_assets.py --src-dir assets --out-dir assets\static_ttfs --force --verify
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
