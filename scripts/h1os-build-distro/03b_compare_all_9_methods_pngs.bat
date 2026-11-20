@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03b] Humidyne Labs - Humiditron epd-font v1.0.23 - All 9 Methods PNG Audit
echo       Workflow   : H1OS Full 108-Strike 9-Pipeline Visual Comparison Audit
echo       Scheme     : scripts\h1os-build-distro\h1os_full.scheme.json (Hardware: esp32s3-N8R8-hw_scheme.json)
echo       Output Dir : build\h1os_9method_audit\inspect_pages\ (per-method + compare_methods)
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow audit --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os_9method_audit" --dist-dir "build\h1os_9method_audit\dist" %*
if errorlevel 1 (
    echo [!] All-9-method visual audit failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] All-9-method visual inspection PNGs generated in build\h1os_9method_audit\inspect_pages\.
if "%EPD_NO_PAUSE%"=="" pause
