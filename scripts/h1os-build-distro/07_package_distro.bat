@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.9 - Package Distribution Bundle
echo      Workflow    : H1OS and humid1-os Firmware Distribution Workflow
echo      Dist Output : dist\h1os_distro\
echo ============================================================================
if not exist "dist\h1os_distro\fonts" mkdir "dist\h1os_distro\fonts"
if not exist "dist\h1os_distro\schemes" mkdir "dist\h1os_distro\schemes"
if not exist "dist\h1os_distro\tools" mkdir "dist\h1os_distro\tools"
if not exist "dist\h1os_distro\metadata" mkdir "dist\h1os_distro\metadata"
if not exist "dist\h1os_distro\licenses" mkdir "dist\h1os_distro\licenses"

copy /y "scripts\h1os-build-distro\*.scheme.json" "dist\h1os_distro\schemes\" >nul
copy /y "tools\fonts\humid1_fw_emit.py" "dist\h1os_distro\tools\" >nul
copy /y "font_icon_epd_patches.json" "dist\h1os_distro\" >nul
copy /y "LICENSE" "dist\h1os_distro\" >nul
if exist "build\metadata\*.json" copy /y "build\metadata\*.json" "dist\h1os_distro\metadata\" >nul
if exist "build\static_ttfs\licenses\*.txt" copy /y "build\static_ttfs\licenses\*.txt" "dist\h1os_distro\licenses\" >nul
if exist "build\h1os\fonts\*.*" xcopy /s /e /y /q "build\h1os\fonts\*" "dist\h1os_distro\fonts\" >nul

echo [+] Packaged self-contained distribution bundle in dist\h1os_distro\.
if "%EPD_NO_PAUSE%"=="" pause
