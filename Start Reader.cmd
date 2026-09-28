@echo off
cd /d "%~dp0"
if exist "runtime\python.exe" (
  "runtime\python.exe" launch.py %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python launch.py %*
  ) else (
    py -3 launch.py %*
  )
)
if errorlevel 1 pause
