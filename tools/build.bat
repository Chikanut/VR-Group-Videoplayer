@echo off
title Quest Deploy Manager - Build

echo.
echo === Quest Deploy Manager - PyInstaller Build ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.x and add to PATH.
    pause
    exit /b 1
)
echo [OK] Python found

echo [..] Installing PyInstaller...
python -m pip install --upgrade pyinstaller >nul 2>&1
echo [OK] PyInstaller ready

if not exist "quest_deploy.py" (
    echo [ERROR] quest_deploy.py not found in current folder.
    echo         Place build.bat next to quest_deploy.py and try again.
    pause
    exit /b 1
)
echo [OK] quest_deploy.py found

if exist "dist\QuestDeployManager.exe" del /f /q "dist\QuestDeployManager.exe"
if exist "build" rmdir /s /q "build"
if exist "QuestDeployManager.spec" del /f /q "QuestDeployManager.spec"

echo [..] Building EXE...
echo.

python -m PyInstaller --onefile --windowed --name "QuestDeployManager" --add-data "deploy_ui;deploy_ui" quest_deploy.py

echo.
if exist "dist\QuestDeployManager.exe" (
    echo [SUCCESS] dist\QuestDeployManager.exe
    explorer dist
) else (
    echo [ERROR] Build failed. Check log above.
)

pause
