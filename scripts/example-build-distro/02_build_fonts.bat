@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [02] Humidyne Labs - Humiditron epd-font v1.0.22 - Build 1-BPP C/H, BDF and Vault
echo      Workflow   : General Embedded Display Example Distribution Workflow
echo      Scheme     : scripts\example-build-distro\example.scheme.json (Hardware: generic_hw.json)
echo      Build Dir  : build\example\
echo      Dist Dir   : dist\example_distro\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow build --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --dist-dir "dist\example_distro" %*
if errorlevel 1 (
    echo [!] Font build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Built 1-BPP C/H fonts into build\example\fonts and Strike Vault into dist\example_distro.
if "%EPD_NO_PAUSE%"=="" pause
