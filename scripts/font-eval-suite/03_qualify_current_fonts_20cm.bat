@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Qualify 03] Humidyne Labs - Humiditron epd-font v1.0.23
echo                   20 cm (200 mm) EPD Legibility Qualification (Current Corpus)
echo                   HW Config : esp32s3-N8R8-hw_scheme.json
echo ============================================================================

python tools\fonts\humid1_font_qualify.py ^
    --hw-scheme esp32s3-N8R8-hw_scheme.json ^
    --src-dir build\static_ttfs ^
    --out-dir build\qualify\static_ttfs ^
    --sizes 12 14 16 18 20 24 ^
    --threshold 128 %*

if %ERRORLEVEL% neq 0 (
    echo [!] Error: 20 cm font qualification failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Per-font Gaussian proof PNGs generated in build\qualify\static_ttfs\gaussian_proofs\.
echo [+] Family weight-pair PNGs generated in build\qualify\static_ttfs\weight_pairs\.
echo [+] Reports and master scorecard generated in build\qualify\static_ttfs\.
exit /b 0
