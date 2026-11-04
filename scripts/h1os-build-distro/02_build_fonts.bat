@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [02] Humidyne Labs - Humiditron epd-font v1.0.8 - Build 1-BPP C/H, BDF and Vault
echo      Workflow : H1OS and humid1-os Firmware Distribution Workflow
echo      Scheme   : scripts\h1os-build-distro\h1os_full.scheme.json
echo      Build    : build\h1os\
echo      Dist     : dist\h1os_distro\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow build --scheme "scripts\h1os-build-distro\h1os_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os" --dist-dir "dist\h1os_distro" --patches font_icon_epd_patches.json %*
if errorlevel 1 (
    echo [!] Font build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Built 1-BPP C/H fonts into build\h1os\fonts and Strike Vault into dist\h1os_distro.
if "%EPD_NO_PAUSE%"=="" pause
