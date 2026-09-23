@echo off
setlocal enabledelayedexpansion
title Voice Clone Reader - Installer
cd /d "%~dp0"

echo ============================================
echo   Voice Clone Reader - Installer
echo ============================================
echo.

REM --- Step 1: find a usable Python (3.9, 3.10, or 3.11) ---
set PYCMD=
for %%V in (3.11 3.10 3.9) do (
    if not defined PYCMD (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 (
            set PYCMD=py -%%V
            echo Found Python %%V
        )
    )
)

if not defined PYCMD (
    echo.
    echo ERROR: Could not find Python 3.9, 3.10, or 3.11 on this system.
    echo This app needs one of those versions ^(not 3.12+^) because of a
    echo dependency limitation.
    echo.
    echo Please install Python 3.11 from:
    echo   https://www.python.org/downloads/
    echo During install, check "Add python.exe to PATH".
    echo Then run this installer again.
    echo.
    pause
    exit /b 1
)

REM --- Step 2: create virtual environment ---
if not exist "venv" (
    echo.
    echo Creating virtual environment...
    %PYCMD% -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo.
    echo Virtual environment already exists, skipping creation.
)

REM --- Step 3: install dependencies ---
echo.
echo Installing dependencies - this can take a while, please be patient...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed. Scroll up to see the error,
    echo and send it to Claude for help if you're not sure what it means.
    pause
    exit /b 1
)

REM --- Step 4: create a desktop shortcut ---
echo.
echo Creating desktop shortcut...
REM If an "app_icon.ico" file exists in this folder, use it for the
REM shortcut; otherwise fall back to a built-in Windows icon.
set ICONPATH=shell32.dll,41
if exist "app_icon.ico" (
    set ICONPATH=%~dp0app_icon.ico
    echo Using custom icon: app_icon.ico
)

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Voice Clone Reader.lnk'));" ^
    "$s.TargetPath = (Resolve-Path 'run_app.bat').Path;" ^
    "$s.WorkingDirectory = (Get-Location).Path;" ^
    "$s.IconLocation = '%ICONPATH%';" ^
    "$s.Save()"

echo.
echo ============================================
echo   Install complete!
echo ============================================
echo A shortcut called "Voice Clone Reader" was added to your Desktop.
echo Double-click it any time to launch the app.
echo.
pause
