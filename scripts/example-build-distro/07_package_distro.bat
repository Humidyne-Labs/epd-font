@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.20 - Package & Zip Distribution Bundle
echo      Workflow    : General Embedded Display Example Workflow
echo      Build Input : build\example\
echo      Dist Output : dist\example_distro\ and dist\epd-font_example_v1.0.20.zip
echo ============================================================================
python tools\fonts\humid1_package_distro.py --build-dir "build\example" --dist-dir "dist\example_distro" --schemes "scripts\example-build-distro\example.scheme.json" --name "example" %*
if errorlevel 1 (
    echo [!] Packaging distribution bundle failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Packaged and zipped portable distribution bundle in dist\example_distro\.
if "%EPD_NO_PAUSE%"=="" pause
