@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================================================
echo [Font-Eval] Step 1: Running Multi-Font ^& Weight Hierarchy Tournament Suite
echo ============================================================================

python tools\fonts\humid1_font_eval.py ^
    --src-dir build\static_ttfs ^
    --out-dir build\font_eval ^
    --sizes 10 12 14 16 20

if %ERRORLEVEL% neq 0 (
    echo [!] Error: Font evaluation benchmark failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Font evaluation report and visual comparison sheet generated in build\font_eval\.
exit /b 0
