@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"

for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "BOLD=%ESC%[1m"
set "RESET=%ESC%[0m"
set "CYAN=%ESC%[36m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "GRAY=%ESC%[90m"

echo.
echo %BOLD%%CYAN%============================================================
echo   ALEX - Patient practice
echo   PMS-selected local and cloud services
echo   Uses your running API - start-platform.bat starts the API
echo ============================================================%RESET%
echo.
set "ALEX_PYTHON=%~dp0..\human-test\.venv\Scripts\python.exe"
if not exist "%ALEX_PYTHON%" (
  echo %RED%[ERROR] Human-test Python environment is missing. Follow start\README.md setup.%RESET%
  set "ALEX_EXIT=1"
  goto done
)
"%ALEX_PYTHON%" -X utf8 "%~dp0launch.py" %*
set "ALEX_EXIT=%ERRORLEVEL%"
:done
if "%ALEX_EXIT%"=="130" (
  echo %RED%[STOP] Launch cancelled by operator.%RESET%
  goto completed
)
if not "%ALEX_EXIT%"=="0" (
  echo %RED%[ERROR] Launcher exited with code %ALEX_EXIT%.%RESET%
  echo %YELLOW%[INFO] If there is no detailed error above, Python may have been forcibly stopped or crashed.%RESET%
  echo %YELLOW%[INFO] Run this batch again after any process-cleanup command has finished.%RESET%
)
:completed
if /I "%~1"=="--check" goto finish
if not "%ALEX_START_NO_PAUSE%"=="1" pause
:finish
exit /b %ALEX_EXIT%
