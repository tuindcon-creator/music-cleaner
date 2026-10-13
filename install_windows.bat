@echo off
setlocal
cd /d "%~dp0"
echo Installing Music Cleaner with Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 64-bit from python.org first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Done. Open run_windows.bat to start.
pause
exit /b 0
:fail
echo Installation failed. Check your Internet connection and the error above.
pause
exit /b 1

