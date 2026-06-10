@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py morning
) else (
  python run.py morning
)
exit /b %ERRORLEVEL%
