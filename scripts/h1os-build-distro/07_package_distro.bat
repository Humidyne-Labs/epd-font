@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.21 - Package and Zip Distribution Bundle
echo      Workflow    : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      HW Config   : esp32s3-N8R8-hw_scheme.json
echo      Build Input : build\h1os\
echo      Dist Output : dist\h1os_distro\ and dist\epd-font_h1os_v1.0.21.zip
echo ============================================================================
python tools\fonts\humid1_package_distro.py --build-dir "build\h1os" --dist-dir "dist\h1os_distro" --hw-scheme "esp32s3-N8R8-hw_scheme.json" --schemes "scripts\h1os-build-distro\h1os_full.scheme.json" "scripts\h1os-build-distro\h1os_lite.scheme.json" --name "h1os" %*
if errorlevel 1 (
    echo [!] Packaging distribution bundle failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Packaged and zipped portable distribution bundle in dist\h1os_distro\.
if "%EPD_NO_PAUSE%"=="" pause
