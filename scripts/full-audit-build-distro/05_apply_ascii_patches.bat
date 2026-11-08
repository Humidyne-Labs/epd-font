@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [05] Humidyne Labs - Humiditron epd-font v1.0.22 - Compile Edited ASCII Patches to Root Patch File
echo      Workflow   : Complete 10px-40px (Step 2px) 9-Pipeline Visual Audit and Distribution Workflow
echo      Input Dir  : build\audit\ascii_patches\
echo      Output File: font_icon_epd_patches.json
echo ============================================================================
python3 tools\fonts\humid1_generate_1bpp.py --workflow patch --apply --ascii-dir "build\audit\ascii_patches" --patches font_icon_epd_patches.json %*
if errorlevel 1 (
    echo [!] Applying ASCII patches failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Compiled modified ASCII patches into root font_icon_epd_patches.json.
if "%EPD_NO_PAUSE%"=="" pause
