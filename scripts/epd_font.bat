@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "VENV_PY=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [!] Missing .venv Python 3.12 environment at "%VENV_PY%".
    echo     Run: powershell -ExecutionPolicy Bypass -File "%~dp0setup_venv.ps1"
    exit /b 2
)
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUNBUFFERED=1"
"%VENV_PY%" "%REPO_ROOT%\runner\epd_font_cli.py" %*
exit /b %ERRORLEVEL%
