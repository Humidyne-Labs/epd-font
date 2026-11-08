@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [04] Humidyne Labs - Humiditron epd-font v1.0.21 - Dump Full-Canvas 1:1 ASCII Patches
echo      Workflow   : Complete 10px-40px (Step 2px) 9-Pipeline Visual Audit and Distribution Workflow
echo      HW Config  : esp32s3-N8R8-hw_scheme.json
echo      Scheme     : scripts\full-audit-build-distro\full_audit_distro.scheme.json
echo      Output Dir : build\audit\ascii_patches\
echo ============================================================================
python tools\fonts\humid1_generate_1bpp.py --workflow patch --dump --hw-scheme "esp32s3-N8R8-hw_scheme.json" --scheme "scripts\full-audit-build-distro\full_audit_distro.scheme.json" --src-dir build\static_ttfs --out-dir "build\audit" --ascii-dir "build\audit\ascii_patches" --patches font_icon_epd_patches.json %*
if errorlevel 1 (
    echo [!] ASCII patch dump failed.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
echo [+] Dumped Full-Canvas 1:1 ASCII glyph files into build\audit\ascii_patches.
if "%EPD_NO_PAUSE%"=="" pause
