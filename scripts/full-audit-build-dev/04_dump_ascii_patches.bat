@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [04] Humidyne Labs / Humiditron epd-font v1.0.7 - Dump Full-Canvas 1:1 ASCII Patches (Full 12-40pt Audit Dev Workflow - All Fonts, Icons & Char PNGs)
echo      Output: build\audit_dev\ascii_patches\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow patch --dump --scheme "scripts\full-audit-build-dev\full_audit.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit_dev" --ascii-dir "build\audit_dev\ascii_patches" --patches epd_font_patches.json %*
if errorlevel 1 (
    echo [!] ASCII patch dump failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Dumped Full-Canvas 1:1 ASCII glyph files into build\audit_dev\ascii_patches.
if "%EPD_NO_PAUSE%"=="" pause
