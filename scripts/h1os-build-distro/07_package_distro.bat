@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.20 - Package & Zip Distribution Bundle
echo      Workflow    : H1OS and humid1-os Firmware Distribution Workflow
echo      Build Input : build\h1os\
echo      Dist Output : dist\h1os_distro\ and dist\epd-font_h1os_v1.0.20.zip
echo ============================================================================
python tools\fonts\humid1_package_distro.py --build-dir "build\h1os" --dist-dir "dist\h1os_distro" --schemes "scripts\h1os-build-distro\*.scheme.json" --name "h1os" %*
if errorlevel 1 (
    echo [!] Packaging distribution bundle failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Packaged and zipped portable distribution bundle in dist\h1os_distro\.
if "%EPD_NO_PAUSE%"=="" pause
