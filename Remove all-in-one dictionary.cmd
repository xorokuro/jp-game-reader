@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if exist "runtime\python.exe" (
  "runtime\python.exe" remove_dictionary.py MDX_ALL
) else (
  where py >nul 2>nul
  if errorlevel 1 (python remove_dictionary.py MDX_ALL) else (py -3 remove_dictionary.py MDX_ALL)
)
echo.
pause
