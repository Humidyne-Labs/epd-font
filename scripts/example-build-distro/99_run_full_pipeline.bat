@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs - Humiditron epd-font v1.0.23 - Full End-to-End Pipeline
echo      Workflow   : General Embedded Display Example Distribution Workflow
echo      Scheme     : scripts\example-build-distro\example.scheme.json (Hardware: generic_hw.json)
echo ============================================================================
call 01_build_static_ttfs.bat
if errorlevel 1 exit /b 1
cd /d "%~dp0..\.."
python tools\fonts\humid1_generate_1bpp.py --workflow all --scheme "scripts\example-build-distro\example.scheme.json" --src-dir build\static_ttfs --out-dir "build\example" --dist-dir "dist\example_distro"
if errorlevel 1 exit /b 1
cd /d "%~dp0"
call 05_apply_ascii_patches.bat
if errorlevel 1 exit /b 1
call 07_package_distro.bat
if errorlevel 1 exit /b 1
echo ============================================================================
echo [+] Full v1.0.23 pipeline completed!
echo     Build Output : build\example\
echo     Dist Bundle  : dist\example_distro\ (and dist\epd-font_example_v1.0.23.zip)
echo ============================================================================
if "%EPD_CI%"=="" pause
