@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [05] Humidyne Labs - Humiditron epd-font v1.0.17 - Compile Edited ASCII Patches to Root Patch File
echo      Input  : build\h1os\ascii_patches\
echo      Output : font_icon_epd_patches.json
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow patch --apply --ascii-dir "build\h1os\ascii_patches" --patches font_icon_epd_patches.json %*
if errorlevel 1 (
    echo [!] Applying ASCII patches failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Compiled modified ASCII patches into root font_icon_epd_patches.json.
if "%EPD_NO_PAUSE%"=="" pause
