@echo off
cd /d "%~dp0"
echo ========================================
echo   Starting MediaFlow Web Application
echo ========================================

if exist .venv\Scripts\python.exe (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

start http://localhost:8000
%PY_BIN% server.py 8000
pause
