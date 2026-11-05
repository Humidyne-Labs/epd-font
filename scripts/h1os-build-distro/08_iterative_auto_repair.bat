@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [08] Humidyne Labs - Humiditron epd-font v1.0.14 - Closed-Loop OpenCV Auto-Repair
echo      Workflow : H1OS and humid1-os Firmware Distribution Workflow
echo      Scheme   : scripts\h1os-build-distro\h1os_full.scheme.json
echo      Output   : build\h1os\inspect_repairs\ and build\h1os\fonts\
echo ============================================================================
python tools\fonts\humid1_bilevel_tuner.py --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --patches font_icon_epd_patches.json --min-stem 2 --engine hybrid %*
if errorlevel 1 (
    echo [!] Closed-loop auto-repair failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Closed-loop 2px+ stem auto-floor and counter repair completed in build\h1os\inspect_repairs.
if "%EPD_NO_PAUSE%"=="" pause
