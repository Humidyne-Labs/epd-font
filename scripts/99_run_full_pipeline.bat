@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================================
echo [epd-font v0.0.6] Running Full End-to-End Pipeline (01 -^> 04 -^> 02 -^> 03 -^> 07)
echo ============================================================================
call "%~dp001_build_static_ttfs.bat" --no-pause
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call "%~dp004_dump_ascii_patches.bat" --no-pause
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call "%~dp002_build_h1os_fonts.bat" --no-pause
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call "%~dp003_visual_check_pngs.bat" --no-pause
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call "%~dp007_package_h1os_deployment.bat" --no-pause
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
echo.
echo [+] Full epd-font v0.0.6 pipeline completed successfully!
if "%CI%"=="" if "%1" NEQ "--no-pause" pause
exit /b 0
