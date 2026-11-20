@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt || exit /b 1
python -m PyInstaller --noconfirm --clean --windowed --name GhosttzzKBot --icon "assets\GhosttzzKBot.ico" ghosttzzkbot.py || exit /b 1
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  choco install innosetup --yes --no-progress || exit /b 1
)
"%ISCC%" installer.iss || exit /b 1
