@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs / Humiditron epd-font v1.0.7 - Full End-to-End Pipeline (H1OS & humid1-os Firmware Distribution Workflow)
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
echo [+] Full pipeline (H1OS & humid1-os Firmware Distribution Workflow) completed!
echo     Build Artifacts : build\h1os\
echo     Dist Bundle     : dist\h1os_distro\
echo ============================================================================
pause
