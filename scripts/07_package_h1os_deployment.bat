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
echo [epd-font v0.0.6] Step 7: Syncing H1OS Deployment Package (dist\h1os_deployment)
echo ============================================================================
if not exist "dist\h1os_deployment\tools\fonts\dist" mkdir "dist\h1os_deployment\tools\fonts\dist"
if not exist "dist\h1os_deployment\tools\fonts\schemes" mkdir "dist\h1os_deployment\tools\fonts\schemes"
if not exist "dist\h1os_deployment\tools\fonts\metadata" mkdir "dist\h1os_deployment\tools\fonts\metadata"
if not exist "dist\h1os_deployment\tools\fonts\licenses" mkdir "dist\h1os_deployment\tools\fonts\licenses"
if not exist "dist\h1os_deployment\include" mkdir "dist\h1os_deployment\include"
copy /Y "tools\fonts\plex_fw_emit.py" "dist\h1os_deployment\tools\fonts\plex_fw_emit.py" >nul
copy /Y "tools\fonts\schemes\*.json" "dist\h1os_deployment\tools\fonts\schemes\" >nul
if exist "build\dist\plex_epd_vault.json.gz" copy /Y "build\dist\plex_epd_vault.json.gz" "dist\h1os_deployment\tools\fonts\dist\plex_epd_vault.json.gz" >nul
if exist "assets\static_ttfs\metadata\unified_icon_names.json" copy /Y "assets\static_ttfs\metadata\unified_icon_names.json" "dist\h1os_deployment\tools\fonts\metadata\unified_icon_names.json" >nul
if exist "LICENSES\*.txt" copy /Y "LICENSES\*.txt" "dist\h1os_deployment\tools\fonts\licenses\" >nul
if exist "build\fonts\plex_fonts.h" copy /Y "build\fonts\plex_fonts.h" "dist\h1os_deployment\include\plex_fonts.h" >nul
if exist "build\fonts\h1os_fonts.h" copy /Y "build\fonts\h1os_fonts.h" "dist\h1os_deployment\include\h1os_fonts.h" >nul
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
