@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [02] Humidyne Labs / Humiditron epd-font v1.0.7 - Build 1-BPP C/H, BDF ^& Vault (Full 12-40pt Master Audit Distro Workflow)
echo      Scheme: scripts\full-audit-build-distro\full_audit_distro.scheme.json
echo      Build : build\audit\
echo      Dist  : dist\audit_distro\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow build --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --dist-dir "dist\audit_distro" --patches epd_font_patches.json %*
if errorlevel 1 (
    echo [!] Font build failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Built 1-BPP C/H fonts into build\audit\fonts and Strike Vault into dist\audit_distro.
if "%EPD_NO_PAUSE%"=="" pause
