@echo off
set "ZXTT_SKIP="
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe (
  set "ZXTT_PY=.venv\Scripts\python.exe"
) else (
  set "ZXTT_PY=python"
)
for /f "delims=" %%i in ('"%ZXTT_PY%" scripts\trading_day_gate.py') do set "ZXTT_GATE=%%i"
if /i "%ZXTT_GATE%"=="SKIP" set "ZXTT_SKIP=1"
exit /b 0
