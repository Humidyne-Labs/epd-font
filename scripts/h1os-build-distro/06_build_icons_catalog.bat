@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [06] Humidyne Labs - Humiditron epd-font v1.0.23 - Rebuild Icon and Font Metadata Catalogs
echo      Workflow   : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      Source Dir : assets\
echo      Output Dir : build\static_ttfs\ and build\metadata\
echo ============================================================================
python tools\fonts\generate_char_manifests.py --static-dir build\static_ttfs --out-dir build\metadata
if errorlevel 1 (
    echo [!] Character manifest generation failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
python tools\fonts\build_static_ttf_assets.py --src-dir assets --out-dir build\static_ttfs --meta-out-dir build\metadata --families icons terminus --force --verify %*
if errorlevel 1 (
    echo [!] Icon catalog rebuild failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Icon and Terminus catalogs updated in build\metadata\.
if "%EPD_NO_PAUSE%"=="" pause
