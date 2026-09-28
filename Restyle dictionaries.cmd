@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if exist "runtime\python.exe" (
  "runtime\python.exe" restyle_dictionaries.py %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (python restyle_dictionaries.py %*) else (py -3 restyle_dictionaries.py %*)
)
echo.
pause
