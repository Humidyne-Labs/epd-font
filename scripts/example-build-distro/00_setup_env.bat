@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [00] Humidyne Labs - Humiditron epd-font v1.0.9 - Environment Setup
echo      Workflow : General Embedded Example Distribution Workflow
echo ============================================================================
python --version
if errorlevel 1 (
    echo [!] Error: Python 3 is not installed or not on PATH.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
python -m pip install --upgrade pip
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0"
echo [+] Dependencies installed successfully.
if "%EPD_NO_PAUSE%"=="" pause
