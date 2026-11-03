@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs / Humiditron epd-font v1.0.7 - Visual Inspection PNGs ^& Screen Audit (H1OS & humid1-os Firmware Distribution Workflow)
echo      Filter: trouble
echo      Output: build\h1os\inspect_pages\ ^& build\h1os\inspect_chars\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow check --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --dist-dir "dist\h1os_distro" --patches epd_font_patches.json --inspect-chars-filter trouble --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\h1os\inspect_pages and build\h1os\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
