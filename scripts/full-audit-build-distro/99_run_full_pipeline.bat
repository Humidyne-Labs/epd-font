@echo off
setlocal
set EPD_NO_PAUSE=1
cd /d "%~dp0"
echo ============================================================================
echo [99] Humidyne Labs - Humiditron epd-font v1.0.11 - Full End-to-End Pipeline
echo      Workflow : Full 12-40pt Master Audit and Distribution Workflow
echo ============================================================================
call 01_build_static_ttfs.bat
if errorlevel 1 exit /b 1
call 04_dump_ascii_patches.bat
if errorlevel 1 exit /b 1
call 08_iterative_auto_repair.bat
if errorlevel 1 exit /b 1
call 05_apply_ascii_patches.bat
if errorlevel 1 exit /b 1
call 02_build_fonts.bat
if errorlevel 1 exit /b 1
call 03_visual_check_pngs.bat
if errorlevel 1 exit /b 1
call 07_package_distro.bat
if errorlevel 1 exit /b 1
echo ============================================================================
echo [+] Full pipeline completed successfully!
echo     Build Artifacts : build\audit\
echo     Dist Bundle     : dist\audit_distro\
echo ============================================================================
pause
