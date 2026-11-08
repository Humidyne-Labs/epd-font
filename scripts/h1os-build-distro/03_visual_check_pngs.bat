@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs - Humiditron epd-font v1.0.22 - Visual Inspection PNGs and Screen Audit
echo      Workflow   : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      Scheme     : scripts\h1os-build-distro\h1os_full.scheme.json (Hardware: esp32s3-N8R8-hw_scheme.json)
echo      Output Dir : build\h1os\inspect_pages\ and build\h1os\inspect_chars\
echo ============================================================================
python3 tools\fonts\humid1_generate_1bpp.py --workflow check --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --dist-dir "dist\h1os_distro" %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\h1os\inspect_pages\.
if "%EPD_NO_PAUSE%"=="" pause
