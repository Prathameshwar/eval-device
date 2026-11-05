@echo off
setlocal
set "PYTHONUTF8=1"
set "PLATFORM_PYTHON=%~dp0..\platform\api\.venv\Scripts\python.exe"
if not exist "%PLATFORM_PYTHON%" (
  echo [ERROR] API dependencies are missing.
  echo Run uv sync --frozen from platform\api, then try again.
  set "PLATFORM_EXIT=1"
  goto done
)
echo [INFO] Checking the API and web UI; starting only services that are not running.
"%PLATFORM_PYTHON%" -X utf8 "%~dp0platform_web.py" %*
set "PLATFORM_EXIT=%ERRORLEVEL%"
:done
if /I "%~1"=="--check" goto finish
if /I "%~1"=="--help" goto finish
if not "%PMS_START_NO_PAUSE%"=="1" pause
:finish
exit /b %PLATFORM_EXIT%
