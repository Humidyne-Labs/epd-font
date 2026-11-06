@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Eval] Step 2: Running External Font Collection Evaluation (eval_fonts)
echo ============================================================================

set "EVAL_DIR=C:\Users\Matt\Documents\GitHub\_backup_archive\epd-font\IBMPlex_Hinted"
if not "%~1"=="" set "EVAL_DIR=%~1"

python tools\fonts\humid1_font_eval.py ^
    --src-dir "%EVAL_DIR%" ^
    --out-dir build\font_eval ^
    --sizes 12 14 16 20 24

if %ERRORLEVEL% neq 0 (
    echo [!] Error: Font evaluation benchmark failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Per-font evaluation PNG sheets generated in build\font_eval\sheets\.
echo [+] Master comparison sheet and reports generated in build\font_eval\.
exit /b 0
