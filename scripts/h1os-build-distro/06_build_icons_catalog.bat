@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [06] Humidyne Labs - Humiditron epd-font v1.0.16 - Rebuild Icon and Font Metadata Catalogs
echo      Output : build\metadata\
echo ============================================================================
python tools\fonts\generate_char_manifests.py
python tools\fonts\build_static_ttf_assets.py --src-dir assets --out-dir build\static_ttfs --meta-out-dir build\metadata --families icons terminus --force --verify %*
if errorlevel 1 (
    echo [!] Icon catalog rebuild failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Icon and Terminus catalogs updated in build\metadata\.
if "%EPD_NO_PAUSE%"=="" pause
