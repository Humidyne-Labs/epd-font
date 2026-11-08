@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Eval 02] Humidyne Labs - Humiditron epd-font v1.0.19c
echo                External Font Directory 8-Pipeline Evaluation
echo ============================================================================

if "%~1"=="" (
    echo [!] Configuration Error: Missing external font directory path argument.
    echo     Usage: 02_run_font_eval.bat ^<path_to_custom_font_dir^> [--sizes 10 12 14 16 20 24] [--threshold 128]
    exit /b 1
)

set "EVAL_DIR=%~1"
shift

python tools\fonts\humid1_font_eval.py ^
    --src-dir "%EVAL_DIR%" ^
    --out-dir build\evals\external_fonts ^
    --sizes 10 12 14 16 20 24 ^
    --threshold 128 %1 %2 %3 %4 %5 %6 %7 %8 %9

if %ERRORLEVEL% neq 0 (
    echo [!] Error: External font evaluation failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Per-font 8-pipeline evaluation PNG sheets generated in build\evals\external_fonts\sheets\.
echo [+] Master comparison sheet and reports generated in build\evals\external_fonts\.
exit /b 0
