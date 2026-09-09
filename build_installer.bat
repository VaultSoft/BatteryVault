@echo off
setlocal
title BatteryVault - Build Installer

echo.
echo  ============================================================
echo   BatteryVault - Build Script
echo  ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.11 from https://python.org
    pause
    exit /b 1
)

echo  [1/3] Installing runtime and build dependencies...
python -m pip install --quiet --upgrade -r "%~dp0requirements.txt" -r "%~dp0requirements-build.txt"
if errorlevel 1 (
    echo  [ERROR] pip install failed.
    pause
    exit /b 1
)

echo  [2/3] Building portable package...
python -B "%~dp0build.py"
if errorlevel 1 (
    echo  [ERROR] Build failed.
    pause
    exit /b 1
)

echo  [3/3] Done.
echo.
pause
