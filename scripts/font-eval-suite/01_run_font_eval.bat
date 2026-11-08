@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Eval 01] Humidyne Labs - Humiditron epd-font v1.0.22
echo                9-Pipeline Evaluation Suite (Static TTF Corpus)
echo                HW Config : esp32s3-N8R8-hw_scheme.json
echo ============================================================================

python tools\fonts\humid1_font_eval.py ^
    --hw-scheme esp32s3-N8R8-hw_scheme.json ^
    --src-dir build\static_ttfs ^
    --out-dir build\evals\static_ttfs ^
    --sizes 10 12 14 16 20 24 ^
    --threshold 128 %*

if %ERRORLEVEL% neq 0 (
    echo [!] Error: Font evaluation benchmark failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Per-font 9-pipeline evaluation PNG sheets generated in build\evals\static_ttfs\sheets\.
echo [+] Master comparison sheet and reports generated in build\evals\static_ttfs\.
exit /b 0
