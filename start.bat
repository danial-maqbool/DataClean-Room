@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run py -3 bootstrap.py once before starting the app.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 pause
