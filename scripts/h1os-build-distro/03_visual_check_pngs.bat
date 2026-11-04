@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs - Humiditron epd-font v1.0.8 - Visual Inspection PNGs and Screen Audit
echo      Workflow : H1OS and humid1-os Firmware Distribution Workflow
echo      Output   : build\h1os\inspect_pages\ and build\h1os\inspect_chars\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow check --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --dist-dir "dist\h1os_distro" --patches font_icon_epd_patches.json --inspect-chars-filter trouble --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\h1os\inspect_pages and build\h1os\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
