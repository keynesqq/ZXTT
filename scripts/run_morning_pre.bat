@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py morning --phase pre
) else (
  python run.py morning --phase pre
)
exit /b %ERRORLEVEL%
