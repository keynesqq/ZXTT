@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py auction
) else (
  python run.py auction
)
exit /b %ERRORLEVEL%
