@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs - Humiditron epd-font v1.0.23 - Package and Zip Distribution Bundle
echo      Workflow    : Complete 10px-40px (Step 2px) 9-Pipeline Visual Audit and Distribution Workflow
echo      Build Input : build\audit\
echo      Dist Output : dist\audit_distro\ and dist\epd-font_audit_v1.0.23.zip
echo ============================================================================
python tools\fonts\humid1_package_distro.py --build-dir "build\audit" --dist-dir "dist\audit_distro" --schemes "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --name "audit" %*
if errorlevel 1 (
    echo [!] Packaging distribution bundle failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Packaged and zipped portable distribution bundle in dist\audit_distro\.
if "%EPD_NO_PAUSE%"=="" pause
