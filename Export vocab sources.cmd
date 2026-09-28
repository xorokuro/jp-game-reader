@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if exist "runtime\python.exe" (
  "runtime\python.exe" vocab_sources.py %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (python vocab_sources.py %*) else (py -3 vocab_sources.py %*)
)
echo.
pause
