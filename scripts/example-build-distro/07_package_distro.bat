@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.9 - Package Distribution Bundle
echo      Workflow    : General Embedded Example Distribution Workflow
echo      Dist Output : dist\example_distro\
echo ============================================================================
if not exist "dist\example_distro\fonts" mkdir "dist\example_distro\fonts"
if not exist "dist\example_distro\schemes" mkdir "dist\example_distro\schemes"
if not exist "dist\example_distro\tools" mkdir "dist\example_distro\tools"
if not exist "dist\example_distro\metadata" mkdir "dist\example_distro\metadata"
if not exist "dist\example_distro\licenses" mkdir "dist\example_distro\licenses"

copy /y "scripts\example-build-distro\*.scheme.json" "dist\example_distro\schemes\" >nul
copy /y "tools\fonts\humid1_fw_emit.py" "dist\example_distro\tools\" >nul
copy /y "font_icon_epd_patches.json" "dist\example_distro\" >nul
copy /y "LICENSE" "dist\example_distro\" >nul
if exist "build\metadata\*.json" copy /y "build\metadata\*.json" "dist\example_distro\metadata\" >nul
if exist "build\static_ttfs\licenses\*.txt" copy /y "build\static_ttfs\licenses\*.txt" "dist\example_distro\licenses\" >nul
if exist "build\example\fonts\*.*" xcopy /s /e /y /q "build\example\fonts\*" "dist\example_distro\fonts\" >nul

echo [+] Packaged self-contained distribution bundle in dist\example_distro\.
if "%EPD_NO_PAUSE%"=="" pause
