@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs / Humiditron epd-font v1.0.7 - Visual Inspection PNGs ^& Screen Audit (Full 12-40pt Audit Dev Workflow - All Fonts, Icons & Char PNGs)
echo      Filter: all
echo      Output: build\audit_dev\inspect_pages\ ^& build\audit_dev\inspect_chars\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow check --scheme "scripts\full-audit-build-dev\full_audit.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit_dev" --dist-dir "dist\audit_dev_distro" --patches epd_font_patches.json --inspect-chars-filter all --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\audit_dev\inspect_pages and build\audit_dev\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
