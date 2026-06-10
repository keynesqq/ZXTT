@echo off
cd /d D:\ZXTT
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py auction
) else (
  python run.py auction
)
exit /b %ERRORLEVEL%
