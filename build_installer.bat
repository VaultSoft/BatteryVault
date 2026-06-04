@echo off
setlocal enabledelayedexpansion
title BatteryVault - Build Installer

echo.
echo  ============================================================
echo   BatteryVault v1.0.0 - Build Script
echo  ============================================================
echo.

:: -- Check Python -------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

:: -- Install/upgrade build dependencies ---------------------------
echo  [1/5] Installing build dependencies...
pip install --quiet --upgrade -r requirements.txt
if errorlevel 1 ( echo  [ERROR] pip install failed. & pause & exit /b 1 )

:: -- Regenerate branded icon -------------------------------------
echo  [2/5] Generating icon...
python make_icon.py >nul 2>&1

:: -- Build with PyInstaller --------------------------------------
echo  [3/5] Building with PyInstaller (this takes ~60-90 seconds)...
pyinstaller BatteryVault.spec --noconfirm --clean
if errorlevel 1 ( echo  [ERROR] PyInstaller build failed. & pause & exit /b 1 )

if not exist "dist\BatteryVault\BatteryVault.exe" (
    echo  [ERROR] Build output not found at dist\BatteryVault\BatteryVault.exe
    pause & exit /b 1
)

:: -- Copy README into the portable folder ------------------------
echo  [4/5] Copying README...
copy /Y "README.txt" "dist\BatteryVault\README.txt" >nul

:: -- Package: BatteryVault.exe, _internal\, README.txt -----------
echo  [5/5] Creating portable ZIP...
if exist "BatteryVault_v1.0.0_Portable.zip" del "BatteryVault_v1.0.0_Portable.zip"

powershell -NoProfile -Command ^
    "$src = 'dist\BatteryVault'; $zip = 'BatteryVault_v1.0.0_Portable.zip';" ^
    "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
    "$z = [System.IO.Compression.ZipFile]::Open((Join-Path (Get-Location) $zip), 'Create');" ^
    "$base = (Resolve-Path $src).Path;" ^
    "Get-ChildItem -Recurse $src | Where-Object { -not $_.PSIsContainer } | ForEach-Object {" ^
    "  $rel = $_.FullName.Substring($base.Length + 1).Replace('\','/');" ^
    "  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($z, $_.FullName, \"BatteryVault/$rel\") | Out-Null };" ^
    "$z.Dispose()"
if errorlevel 1 ( echo  [ERROR] ZIP creation failed. & pause & exit /b 1 )

echo.
echo  ------------------------------------------------------------
echo   Done!  Portable ZIP: BatteryVault_v1.0.0_Portable.zip
echo    Contents: BatteryVault.exe  _internal\  README.txt
echo  ------------------------------------------------------------
echo.
pause
