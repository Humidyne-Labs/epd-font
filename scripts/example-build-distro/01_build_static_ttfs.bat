@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [01] Humidyne Labs - Humiditron epd-font v1.0.14 - Build Static TTFs and Metadata
echo      Output : build\static_ttfs\ and build\metadata\
echo ============================================================================
python tools\fonts\build_static_ttf_assets.py --src-dir assets --out-dir build\static_ttfs --meta-out-dir build\metadata --verify %*
if errorlevel 1 (
    echo [!] Static TTF asset build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Static TTF assets and metadata JSON catalogs verified in build\static_ttfs and build\metadata.
if "%EPD_NO_PAUSE%"=="" pause
