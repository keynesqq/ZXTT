@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py evening
) else (
  python run.py evening
)
exit /b %ERRORLEVEL%
