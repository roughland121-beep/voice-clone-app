@echo off
setlocal
title Voice Clone Reader - Build Portable EXE
cd /d "%~dp0"

echo ================================================================
echo   Voice Clone Reader - Build Portable EXE
echo ================================================================
echo This turns the app into a folder you can copy to any Windows PC
echo and run without installing Python. It does NOT need internet
echo access afterward (except for auto-translate and first-time model
echo download).
echo.
echo NOTE: this packages PyTorch + the TTS engine, so the output folder
echo will be several GB and the build itself can take 10-20+ minutes.
echo That is normal - do not close this window while it's working.
echo ================================================================
echo.

if not exist "venv" (
    echo ERROR: No "venv" folder found. Run install.bat first so all
    echo dependencies are installed, then run this script again.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Installing PyInstaller...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building VoiceCloneReader.exe - this will take a while...
pyinstaller --noconfirm --onedir --windowed ^
    --name "VoiceCloneReader" ^
    --collect-all TTS ^
    --collect-all torch ^
    --collect-all torchaudio ^
    --collect-all torch_directml ^
    --collect-all transformers ^
    --collect-all sounddevice ^
    --collect-all soundfile ^
    --collect-all pydub ^
    --collect-all imageio_ffmpeg ^
    --collect-all deep_translator ^
    --hidden-import=torch_directml ^
    main.py

if errorlevel 1 (
    echo.
    echo ================================================================
    echo   Build FAILED. Scroll up to see the actual error and send it
    echo   to Claude for help - PyInstaller + PyTorch builds are finicky
    echo   and the fix is almost always a missing --collect-all for
    echo   whatever package the error mentions.
    echo ================================================================
    pause
    exit /b 1
)

echo.
echo Copying extra files into the build...
if not exist "dist\VoiceCloneReader\saved_voice_samples" mkdir "dist\VoiceCloneReader\saved_voice_samples"
if exist "urdu_model" (
    echo Copying urdu_model folder ^(this may take a minute, it's large^)...
    xcopy /E /I /Y "urdu_model" "dist\VoiceCloneReader\urdu_model" >nul
) else (
    echo NOTE: no "urdu_model" folder found here, so Urdu support will not
    echo be included. You can add it later by copying an "urdu_model"
    echo folder next to VoiceCloneReader.exe.
)

echo.
echo ================================================================
echo   Done! Your portable app is at:
echo   dist\VoiceCloneReader\VoiceCloneReader.exe
echo.
echo   Copy the WHOLE "dist\VoiceCloneReader" folder to wherever you
echo   want (a USB drive, another PC, etc.) and double-click the .exe
echo   inside it to run the app - no Python install required there.
echo ================================================================
pause
