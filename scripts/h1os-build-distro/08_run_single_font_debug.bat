@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [08] Humidyne Labs - Humiditron epd-font v1.0.22 - Single-Font Full Debug Verification
echo      Scheme     : scripts\h1os-build-distro\h1os_debug.scheme.json
echo      Features   : 1 Font (IBM Plex Sans Normal 16px and 38px), pipeline=all-debug,
echo                   sheet_debug=true, char_debug=true, debug_stages=true
echo      Output Dir : build\h1os_debug\
echo ============================================================================
python3 tools\fonts\humid1_generate_1bpp.py --workflow audit --scheme "scripts\h1os-build-distro\h1os_debug.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os_debug" --dist-dir "dist\h1os_debug_distro" %*
if errorlevel 1 (
    echo [!] Single-font debug verification failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Single-font full debug verification complete in build\h1os_debug\!
if "%EPD_NO_PAUSE%"=="" pause
