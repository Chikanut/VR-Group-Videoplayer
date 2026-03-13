@echo off
title VR Classroom Control Panel
cd /d "%~dp0"

echo ============================================
echo   VR Classroom Control Panel
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.10+ from https://www.python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Install Python dependencies if needed
if not exist "App\venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv App\venv
)

echo [SETUP] Activating virtual environment...
call App\venv\Scripts\activate.bat

echo [SETUP] Installing/updating dependencies...
pip install -q -r App\requirements.txt

:: Build frontend before starting the server so the served dist stays in sync
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found! Please install Node.js and ensure npm is available in PATH.
    pause
    exit /b 1
)

set "FULL_FRONTEND_REBUILD=0"
set /p FULL_FRONTEND_REBUILD="Run full frontend rebuild (delete node_modules and package-lock.json)? [y/N]: "
if /I "%FULL_FRONTEND_REBUILD%"=="y" (
    echo [SETUP] Removing frontend node_modules and package-lock.json...
    if exist "App\frontend\node_modules" rmdir /s /q "App\frontend\node_modules"
    if exist "App\frontend\package-lock.json" del /f /q "App\frontend\package-lock.json"
)

if exist "App\frontend\dist" (
    echo [SETUP] Removing old frontend dist...
    rmdir /s /q "App\frontend\dist"
)

if not exist "App\frontend\node_modules" (
    echo [SETUP] Installing frontend dependencies...
    pushd App\frontend
    call npm install
    if errorlevel 1 (
        popd
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
    popd
)

echo [SETUP] Building frontend...
pushd App\frontend
call npm run build
if errorlevel 1 (
    popd
    echo [ERROR] Frontend build failed.
    pause
    exit /b 1
)
popd

echo.
echo [START] Starting server...
echo [INFO]  Opening http://localhost:8000 in your default browser
echo [INFO]  Press Ctrl+C to stop
echo.

start "" http://localhost:8000

cd App
python run.py
pause
