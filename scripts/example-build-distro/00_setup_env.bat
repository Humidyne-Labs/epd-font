@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [00] Humidyne Labs - Humiditron epd-font v1.0.19c - Environment Setup
echo      Workflow : General Embedded Example Distribution Workflow
echo ============================================================================
python --version
if errorlevel 1 (
    echo [!] Error: Python 3 is not installed or not on PATH.
    if "%EPD_NO_PAUSE%"=="" pause
    exit /b 1
)
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0" "numpy>=1.24.0" "opencv-python>=4.8.0"
python -m pip install "pyopencl>=2023.1" || echo [*] Optional PyOpenCL GPU backend skipped (no OpenCL ICD build headers); OpenCV UMat / CPU backend active.
echo [+] Dependencies installed successfully.
if "%EPD_NO_PAUSE%"=="" pause
