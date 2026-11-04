@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [08] Humidyne Labs - Humiditron epd-font v1.0.11 - Closed-Loop OpenCV Auto-Repair
echo      Workflow : General Embedded Example Distribution Workflow
echo      Scheme   : scripts\example-build-distro\example.scheme.json
echo      Output   : build\example\inspect_repairs\ and build\example\fonts\
echo ============================================================================
python tools\fonts\humid1_bilevel_tuner.py --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --patches font_icon_epd_patches.json --min-stem 2 --engine hybrid %*
if errorlevel 1 (
    echo [!] Closed-loop auto-repair failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Closed-loop >=2px stem auto-floor and counter repair completed in build\example\inspect_repairs.
if "%EPD_NO_PAUSE%"=="" pause
