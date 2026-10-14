@echo off
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2]==(3,11); import PySide6,psutil,torch,demucs,imageio_ffmpeg,sherpa_onnx; assert sherpa_onnx.__version__=='1.13.8'" >nul 2>&1
if errorlevel 1 goto setup
goto launch
:setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
:launch
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
