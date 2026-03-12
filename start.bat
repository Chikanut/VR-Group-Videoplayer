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

echo.
echo [START] Starting server...
echo [INFO]  Opening http://localhost:8000 in your default browser
echo [INFO]  Press Ctrl+C to stop
echo.

start "" http://localhost:8000

cd App
python run.py
pause
