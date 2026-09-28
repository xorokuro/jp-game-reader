@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if exist "runtime\python.exe" (
  "runtime\python.exe" add_dictionaries.py
) else (
  where py >nul 2>nul
  if errorlevel 1 (python add_dictionaries.py) else (py -3 add_dictionaries.py)
)
echo.
pause
