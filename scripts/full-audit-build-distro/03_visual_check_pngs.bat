@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs - Humiditron epd-font v1.0.14 - Visual Inspection PNGs and Screen Audit
echo      Workflow : Full 12-40pt Master Audit and Distribution Workflow
echo      Output   : build\audit\inspect_pages\ and build\audit\inspect_chars\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow check --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --dist-dir "dist\audit_distro" --patches font_icon_epd_patches.json --inspect-chars-filter all --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\audit\inspect_pages and build\audit\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
