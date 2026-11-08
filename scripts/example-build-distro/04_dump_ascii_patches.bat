@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [04] Humidyne Labs - Humiditron epd-font v1.0.21 - Dump Full-Canvas 1:1 ASCII Patches
echo      Workflow   : General Embedded Display Example Distribution Workflow
echo      HW Config  : generic_hw.json
echo      Scheme     : scripts\example-build-distro\example.scheme.json
echo      Output Dir : build\example\ascii_patches\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow patch --dump --hw-scheme "generic_hw.json" --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --ascii-dir "build\example\ascii_patches" --patches font_icon_epd_patches.json %*
if errorlevel 1 (
    echo [!] ASCII patch dump failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Dumped Full-Canvas 1:1 ASCII glyph files into build\example\ascii_patches.
if "%EPD_NO_PAUSE%"=="" pause
