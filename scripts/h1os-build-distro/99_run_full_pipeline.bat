@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs - Humiditron epd-font v1.0.20 - Full End-to-End Pipeline
echo      Workflow : H1OS and humid1-os Firmware Distribution Workflow
echo ============================================================================
call 01_build_static_ttfs.bat
if errorlevel 1 exit /b 1
call 02_build_fonts.bat
if errorlevel 1 exit /b 1
call 03_visual_check_pngs.bat
if errorlevel 1 exit /b 1
call 04_dump_ascii_patches.bat
if errorlevel 1 exit /b 1
call 05_apply_ascii_patches.bat
if errorlevel 1 exit /b 1
call 07_package_distro.bat
if errorlevel 1 exit /b 1
echo ============================================================================
echo [+] Full v1.0.20 pipeline completed!
echo     Build Output : build\h1os\
echo     Dist Bundle  : dist\h1os_distro\ (and dist\epd-font_h1os_v1.0.20.zip)
echo ============================================================================
if "%EPD_CI%"=="" pause
