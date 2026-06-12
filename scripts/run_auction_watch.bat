@echo off
REM 兼容旧计划任务：仅跑竞价段（正式交易请用 run_intraday_watch.bat）
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py intraday --session auction
) else (
  python run.py intraday --session auction
)
exit /b %ERRORLEVEL%
