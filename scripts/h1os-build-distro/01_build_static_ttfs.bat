@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [01] Humidyne Labs - Humiditron epd-font v1.0.21 - Build Static TTFs and Metadata
echo      Workflow   : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      Source Dir : assets\
echo      Output Dir : build\static_ttfs\ and build\metadata\
echo ============================================================================
python tools\fonts\build_static_ttf_assets.py --src-dir assets --out-dir build\static_ttfs --meta-out-dir build\metadata --verify %*
if errorlevel 1 (
    echo [!] Static TTF asset build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Static TTF assets (113 binaries) and metadata JSON catalogs verified in build\static_ttfs and build\metadata.
if "%EPD_NO_PAUSE%"=="" pause
