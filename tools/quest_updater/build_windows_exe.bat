@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   VR Quest Updater - Windows EXE Build
echo ============================================

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

if not exist "venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 exit /b 1
)

call venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

echo [SETUP] Installing build dependencies...
pip install -q -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [BUILD] Building Windows executable with PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --noconfirm --clean --onefile --windowed --name VRQuestUpdater run.py
if errorlevel 1 exit /b 1

echo.
echo [DONE] Build completed.
echo [DONE] EXE: %CD%\dist\VRQuestUpdater.exe

endlocal
