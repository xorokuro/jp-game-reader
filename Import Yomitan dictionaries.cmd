@echo off
cd /d "%~dp0"
echo Importing Yomitan dictionaries listed in dictionaries\yomitan-paths.txt ...
if exist runtime\python.exe (runtime\python.exe yomitan_library.py) else (py -3 yomitan_library.py || python yomitan_library.py)
pause
