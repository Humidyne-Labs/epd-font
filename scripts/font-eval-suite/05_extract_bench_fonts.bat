@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Qualify 05] Humidyne Labs - Humiditron epd-font v1.0.23
echo                   Extract Clean TTFs + Licenses (Strip Metadata)
echo                   Source    : assets\bench_assets
echo                   Output    : build\bench_test_fonts
echo ============================================================================

python tools\fonts\extract_bench_fonts.py ^
    --src-dir assets\bench_assets ^
    --out-dir build\bench_test_fonts ^
    --clean %*

if %ERRORLEVEL% neq 0 (
    echo [!] Error: Bench font extraction failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Extracted clean qualification test directory in build\bench_test_fonts\.
echo     Qualify one category : scripts\font-eval-suite\04_qualify_external_font_dir_20cm.bat build\bench_test_fonts\monospace
echo     Qualify all categories: scripts\font-eval-suite\04_qualify_external_font_dir_20cm.bat build\bench_test_fonts
exit /b 0
