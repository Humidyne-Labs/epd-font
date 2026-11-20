@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs - Humiditron epd-font v1.0.23 - Full End-to-End Pipeline
echo      Workflow   : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      Scheme     : scripts\h1os-build-distro\h1os_full.scheme.json (Hardware: esp32s3-N8R8-hw_scheme.json)
echo ============================================================================
call 01_build_static_ttfs.bat
if errorlevel 1 exit /b 1
cd /d "%~dp0..\.."
python tools\fonts\humid1_generate_1bpp.py --workflow all --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --dist-dir "dist\h1os_distro"
if errorlevel 1 exit /b 1
cd /d "%~dp0"
call 05_apply_ascii_patches.bat
if errorlevel 1 exit /b 1
call 07_package_distro.bat
if errorlevel 1 exit /b 1
echo ============================================================================
echo [+] Full v1.0.23 pipeline completed!
echo     Build Output : build\h1os\
echo     Dist Bundle  : dist\h1os_distro\ (and dist\epd-font_h1os_v1.0.23.zip)
echo ============================================================================
if "%EPD_CI%"=="" pause
