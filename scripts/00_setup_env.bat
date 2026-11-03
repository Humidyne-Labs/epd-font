@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
echo ============================================================================
echo [epd-font v0.0.6] Setting up Python Virtual Environment (.venv)...
echo ============================================================================
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "SYS_PY=python"
) else (
    set "SYS_PY=py -3"
)
if not exist ".venv\Scripts\python.exe" (
    %SYS_PY% -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0"
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
