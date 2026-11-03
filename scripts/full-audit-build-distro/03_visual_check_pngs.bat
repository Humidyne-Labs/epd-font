@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs / Humiditron epd-font v1.0.7 - Visual Inspection PNGs ^& Screen Audit (Full 12-40pt Master Audit Distro Workflow)
echo      Filter: trouble
echo      Output: build\audit\inspect_pages\ ^& build\audit\inspect_chars\
echo ============================================================================
python tools\fonts\generate_plex_1bpp.py --workflow check --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --dist-dir "dist\audit_distro" --patches epd_font_patches.json --inspect-chars-filter trouble --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs generated in build\audit\inspect_pages and build\audit\inspect_chars.
if "%EPD_NO_PAUSE%"=="" pause
