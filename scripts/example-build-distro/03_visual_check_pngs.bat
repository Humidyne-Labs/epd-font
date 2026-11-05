@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs - Humiditron epd-font v1.0.14 - Visual Inspection PNGs and Screen Audit
echo      Workflow : General Embedded Example Distribution Workflow
echo      Output   : build\example\inspect_pages\ and build\example\inspect_chars\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow check --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --dist-dir "dist\example_distro" --patches font_icon_epd_patches.json --inspect-chars-filter all --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\example\inspect_pages and build\example\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
