@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py midday
) else (
  python run.py midday
)
exit /b %ERRORLEVEL%
