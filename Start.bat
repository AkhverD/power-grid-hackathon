@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul
python start.py %*
set "RC=%errorlevel%"
if "%~1"=="" pause
exit /b %RC%
