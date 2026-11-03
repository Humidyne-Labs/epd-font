@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [02] Humidyne Labs / Humiditron epd-font v1.0.7 - Build 1-BPP C/H, BDF ^& Vault (General Embedded Example Distribution Workflow)
echo      Scheme: scripts\example-build-distro\example.scheme.json
echo      Build : build\example\
echo      Dist  : dist\example_distro\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow build --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --dist-dir "dist\example_distro" --patches epd_font_patches.json %*
if errorlevel 1 (
    echo [!] Font build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Built 1-BPP C/H fonts into build\example\fonts and Strike Vault into dist\example_distro.
if "%EPD_NO_PAUSE%"=="" pause
