@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [05] Humidyne Labs / Humiditron epd-font v1.0.7 - Compile Edited ASCII Patches -> Root Patch File
echo      Input : build\example\ascii_patches\
echo      Output: epd_font_patches.json (Root-Tracked Git Patch Manifest)
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow patch --apply --ascii-dir "build\example\ascii_patches" --patches epd_font_patches.json %*
if errorlevel 1 (
    echo [!] Applying ASCII patches failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
copy /y epd_font_patches.json tools\fonts\plex_epd_patches.json >nul
echo [+] Compiled modified ASCII patches into root epd_font_patches.json.
if "%EPD_NO_PAUSE%"=="" pause
