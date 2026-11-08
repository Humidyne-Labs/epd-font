@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [03] Humidyne Labs - Humiditron epd-font v1.0.21 - Visual Inspection PNGs and Screen Audit
echo      Workflow   : Complete 10px-40px (Step 2px) 9-Pipeline Visual Audit and Distribution Workflow
echo      HW Config  : esp32s3-N8R8-hw_scheme.json
echo      Scheme     : scripts\full-audit-build-distro\full_audit_distro.scheme.json
echo      Output Dir : build\audit\inspect_pages\ and build\audit\inspect_chars\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow audit --hw-scheme "esp32s3-N8R8-hw_scheme.json" --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --dist-dir "dist\audit_distro" --patches font_icon_epd_patches.json --sheet-debug --audit-screens %*
if errorlevel 1 (
    echo [!] Visual check failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Visual inspection PNGs and screen audit generated in build\audit\inspect_pages and build\audit\screen_audit.
if "%EPD_NO_PAUSE%"=="" pause
