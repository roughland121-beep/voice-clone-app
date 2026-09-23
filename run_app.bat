@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist "%~dp0venv\Scripts\python.exe" (
    echo.
    echo ERROR: Could not find venv\Scripts\python.exe
    echo It looks like install.bat hasn't been run yet, or was run in a
    echo different folder. Run install.bat first, then try this again.
    echo.
    pause
    exit /b 1
)

"%~dp0venv\Scripts\python.exe" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo The app closed with an error - see above for details.
    pause
)

