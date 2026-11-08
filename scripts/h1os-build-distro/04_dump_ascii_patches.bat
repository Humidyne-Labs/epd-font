@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [04] Humidyne Labs - Humiditron epd-font v1.0.22 - Dump Full-Canvas 1:1 ASCII Patches
echo      Workflow   : H1OS and humid1-os Firmware Distribution Workflow (ESP32-S3-N8R8)
echo      Scheme     : scripts\h1os-build-distro\h1os_full.scheme.json (Hardware: esp32s3-N8R8-hw_scheme.json)
echo      Output Dir : build\h1os\ascii_patches\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow patch --dump --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" %*
if errorlevel 1 (
    echo [!] ASCII patch dump failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Dumped Full-Canvas 1:1 ASCII glyph files into build\h1os\ascii_patches.
if "%EPD_NO_PAUSE%"=="" pause
