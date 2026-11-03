@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================================
echo [07] Humidyne Labs / Humiditron epd-font v1.0.7 - Package Distribution Bundle (Full 12-40pt Master Audit Distro Workflow)
echo      Dist Output: dist\audit_distro\
echo ============================================================================
if not exist "dist\audit_distro\fonts" mkdir "dist\audit_distro\fonts"
if not exist "dist\audit_distro\schemes" mkdir "dist\audit_distro\schemes"
if not exist "dist\audit_distro\tools" mkdir "dist\audit_distro\tools"
if not exist "dist\audit_distro\metadata" mkdir "dist\audit_distro\metadata"
if not exist "dist\audit_distro\licenses" mkdir "dist\audit_distro\licenses"

copy /y "scripts\full-audit-build-distro\*.scheme.json" "dist\audit_distro\schemes\" >nul
copy /y "tools\fonts\plex_fw_emit.py" "dist\audit_distro\tools\" >nul
copy /y "epd_font_patches.json" "dist\audit_distro\" >nul
copy /y "LICENSE" "dist\audit_distro\" >nul
if exist "build\metadata\*.json" copy /y "build\metadata\*.json" "dist\audit_distro\metadata\" >nul
if exist "build\static_ttfs\licenses\*.txt" copy /y "build\static_ttfs\licenses\*.txt" "dist\audit_distro\licenses\" >nul
if exist "build\audit\fonts\*.*" xcopy /s /e /y /q "build\audit\fonts\*" "dist\audit_distro\fonts\" >nul

echo [+] Packaged self-contained distribution bundle in dist\audit_distro\.
if "%EPD_NO_PAUSE%"=="" pause
