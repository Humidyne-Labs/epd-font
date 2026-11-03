@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs / Humiditron epd-font v1.0.7 - Visual Inspection PNGs ^& Screen Audit (General Embedded Example Distribution Workflow)
echo      Filter: trouble
echo      Output: build\example\inspect_pages\ ^& build\example\inspect_chars\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow check --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --dist-dir "dist\example_distro" --patches epd_font_patches.json --inspect-chars-filter trouble --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\example\inspect_pages and build\example\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
