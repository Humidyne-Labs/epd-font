@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [10] Humidyne Labs - Humiditron epd-font v1.0.23 - Build and Package H1OS v2
echo      Workflow   : H1OS v2 (20 cm Gaussian-PSF Qualified Typography Package)
echo      Scheme     : scripts\h1os-build-distro\h1os_v2_full.scheme.json
echo      Build Dir  : build\h1os_v2\
echo      Dist Dir   : dist\h1os_v2_distro\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow build --scheme "scripts\h1os-build-distro\h1os_v2_full.scheme.json" --src-dir build\static_ttfs --out-dir "build\h1os_v2" --dist-dir "dist\h1os_v2_distro" %*
if errorlevel 1 (
    echo [!] H1OS v2 font build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
python tools\fonts\humid1_package_distro.py --build-dir "build\h1os_v2" --dist-dir "dist\h1os_v2_distro" --schemes "scripts\h1os-build-distro\h1os_v2_full.scheme.json" "scripts\h1os-build-distro\h1os_v2_lite.scheme.json" --name "h1os_v2"
if errorlevel 1 (
    echo [!] H1OS v2 distribution packaging failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Built and packaged H1OS v2 distribution bundle in dist\h1os_v2_distro\.
if "%EPD_NO_PAUSE%"=="" pause
