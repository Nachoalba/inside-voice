@echo off
REM Builds Inside Voice on Windows: tests -> InsideVoice.exe -> installer.
REM Needs Python 3.10+ (64-bit). Inno Setup 6 is optional (only for the installer).
setlocal
cd /d "%~dp0"

python -m pip install -r requirements-dev.txt || goto :error
python -m pytest || goto :error
python -m inside_voice --selftest || goto :error
python -m PyInstaller --noconfirm inside-voice.spec || goto :error

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    "%ISCC%" installer\inside-voice.iss || goto :error
    echo.
    echo Installer ready in dist-installer\
) else (
    echo.
    echo Inno Setup 6 not found: skipping the installer. The portable app is in dist\InsideVoice\
)
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
