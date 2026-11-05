@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [08] Humidyne Labs - Humiditron epd-font v1.0.15 - Closed-Loop OpenCV Auto-Repair
echo      Workflow : Full 12-40px Master Audit and Distribution Workflow
echo      Scheme   : scripts\full-audit-build-distro\full_audit_distro.scheme.json
echo      Output   : build\audit\inspect_repairs\ and build\audit\fonts\
echo ============================================================================
python tools\fonts\humid1_bilevel_tuner.py --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --patches font_icon_epd_patches.json --min-stem 2 --engine hybrid %*
if errorlevel 1 (
    echo [!] Closed-loop auto-repair failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Closed-loop 2px+ stem auto-floor and counter repair completed in build\audit\inspect_repairs.
if "%EPD_NO_PAUSE%"=="" pause
