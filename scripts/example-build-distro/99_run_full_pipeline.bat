@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs / Humiditron epd-font v1.0.7 - Full End-to-End Pipeline (General Embedded Example Distribution Workflow)
echo ============================================================================
call 01_build_static_ttfs.bat
if errorlevel 1 exit /b 1
call 02_build_fonts.bat
if errorlevel 1 exit /b 1
call 03_visual_check_pngs.bat
if errorlevel 1 exit /b 1
call 04_dump_ascii_patches.bat
if errorlevel 1 exit /b 1
call 07_package_distro.bat
if errorlevel 1 exit /b 1
echo ============================================================================
echo [+] Full pipeline (General Embedded Example Distribution Workflow) completed!
echo     Build Artifacts : build\example\
echo     Dist Bundle     : dist\example_distro\
echo ============================================================================
pause
