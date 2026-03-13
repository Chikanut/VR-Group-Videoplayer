@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   VR Classroom - Windows EXE Build
echo ============================================

set "ICON_PATH=assets\icons\app.ico"

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

echo [SETUP] Installing Python dependencies...
pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Node.js is required to build frontend assets.
    exit /b 1
)

set "FULL_FRONTEND_REBUILD=0"
set /p FULL_FRONTEND_REBUILD="Run full frontend rebuild (delete node_modules and package-lock.json)? [y/N]: "
if /I "%FULL_FRONTEND_REBUILD%"=="y" (
    echo [BUILD] Removing frontend node_modules and package-lock.json...
    if exist "frontend\node_modules" rmdir /s /q "frontend\node_modules"
    if exist "frontend\package-lock.json" del /f /q "frontend\package-lock.json"
)

if exist "frontend\dist" (
    echo [BUILD] Removing old frontend dist...
    rmdir /s /q "frontend\dist"
)

echo [BUILD] Building frontend...
pushd frontend
call npm install
if errorlevel 1 (
    popd
    exit /b 1
)
call npm run build
if errorlevel 1 (
    popd
    exit /b 1
)
popd

echo [BUILD] Building Windows executable with PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

if not exist "%ICON_PATH%" (
    echo [WARN ] EXE icon not found at %CD%\%ICON_PATH%
    echo [WARN ] Build will continue with default icon.
    set "PYINSTALLER_ICON_ARG="
) else (
    echo [BUILD] Using EXE icon: %CD%\%ICON_PATH%
    set "PYINSTALLER_ICON_ARG=--icon %ICON_PATH%"
)

pyinstaller --noconfirm --clean --onefile --name VRClassroomControl --add-data "frontend/dist;frontend/dist" %PYINSTALLER_ICON_ARG% run.py
if errorlevel 1 exit /b 1

echo.
echo [DONE] Build completed.
echo [DONE] EXE: %CD%\dist\VRClassroomControl.exe
echo [TIP ] Share dist\VRClassroomControl.exe with users.

endlocal
