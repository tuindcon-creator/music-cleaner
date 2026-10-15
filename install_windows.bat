@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if errorlevel 1 (
  echo Setup failed. Read the message above.
  pause
  exit /b 1
)
echo Ready. Open run_windows.bat to start Music Cleaner.
pause
