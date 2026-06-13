@echo off
call "%~dp0_begin_if_trading_day.bat"
if defined ZXTT_SKIP exit /b 0
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py morning --phase pre
) else (
  python run.py morning --phase pre
)
exit /b %ERRORLEVEL%
