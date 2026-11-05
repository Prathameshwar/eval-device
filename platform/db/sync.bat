@echo off
setlocal
set "PYTHONUTF8=1"
if not exist "%~dp0..\api\.venv\Scripts\python.exe" (
  echo Install the API environment with uv sync first.
  exit /b 1
)
"%~dp0..\api\.venv\Scripts\python.exe" "%~dp0sync.py" %*
exit /b %ERRORLEVEL%
