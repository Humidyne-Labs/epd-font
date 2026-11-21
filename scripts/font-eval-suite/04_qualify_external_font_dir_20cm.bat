@echo off
setlocal
for %%R in ("%~dp0..\..") do set "REPO_ROOT=%%~fR"

echo ============================================================================
echo [Font-Qualify 04] Humidyne Labs - Humiditron epd-font v1.0.23
echo                   External Font Directory 20 cm EPD Qualification
echo                   HW Config : esp32s3-N8R8-hw_scheme.json
echo ============================================================================

if "%~1"=="" (
    echo [!] Configuration Error: Missing external font directory path argument.
    echo     Usage: 04_qualify_external_font_dir_20cm.bat ^<path_to_custom_font_dir^> [--sizes 12 14 16 18 20 24] [--pipelines otsu-adaptive raw-hinted]
    echo        Or: 04_qualify_external_font_dir_20cm.bat --src-dir ^<dir^> --out-dir ^<dir^> [extra flags...]
    exit /b 1
)

set "FIRST_ARG=%~1"
if "%FIRST_ARG:~0,1%"=="-" goto :flag_passthrough

:strip_slash
if not "%FIRST_ARG%"=="" if "%FIRST_ARG:~-1%"=="\" (
    set "FIRST_ARG=%FIRST_ARG:~0,-1%"
    goto :strip_slash
)
if not "%FIRST_ARG%"=="" if "%FIRST_ARG:~-1%"=="/" (
    set "FIRST_ARG=%FIRST_ARG:~0,-1%"
    goto :strip_slash
)

if "%FIRST_ARG%"=="" set "FIRST_ARG=."
for %%I in ("%FIRST_ARG%") do (
    set "EVAL_DIR=%%~fI"
    set "DIR_SLUG=%%~nxI"
)
if "%EVAL_DIR:~-1%"=="\" if /i not "%EVAL_DIR:~1,2%"==":\" set "EVAL_DIR=%EVAL_DIR:~0,-1%"
if "%DIR_SLUG%"=="" set "DIR_SLUG=external_fonts"
shift

echo     Source    : %EVAL_DIR%
echo     Output    : build\qualify\%DIR_SLUG%
echo ============================================================================

cd /d "%REPO_ROOT%"
python tools\fonts\humid1_font_qualify.py ^
    --hw-scheme esp32s3-N8R8-hw_scheme.json ^
    --src-dir "%EVAL_DIR%" ^
    --out-dir "build\qualify\%DIR_SLUG%" ^
    --sizes 12 14 16 18 20 24 ^
    --threshold 128 %1 %2 %3 %4 %5 %6 %7 %8 %9

if %ERRORLEVEL% neq 0 (
    echo [!] Error: External font qualification failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo [+] Per-font Gaussian proof PNGs generated in build\qualify\%DIR_SLUG%\gaussian_proofs\.
echo [+] Family weight-pair PNGs generated in build\qualify\%DIR_SLUG%\weight_pairs\.
echo [+] Reports and master scorecard generated in build\qualify\%DIR_SLUG%\.
exit /b 0

:flag_passthrough
echo     Mode      : Flag passthrough (%*)
echo ============================================================================
python "%REPO_ROOT%\tools\fonts\humid1_font_qualify.py" ^
    --hw-scheme "%REPO_ROOT%\esp32s3-N8R8-hw_scheme.json" %*

if %ERRORLEVEL% neq 0 (
    echo [!] Error: External font qualification failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)
exit /b 0
