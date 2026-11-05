@echo off
setlocal
set "HUMAN_BUILD_PYTHON=%~dp0..\human-test\.venv\Scripts\python.exe"
if not exist "%HUMAN_BUILD_PYTHON%" (
  echo Human-test build environment is missing. Run human-test\setup.bat first.
  exit /b 1
)
"%HUMAN_BUILD_PYTHON%" -X utf8 "%~dp0build_human_test.py" %* 2>&1
exit /b %ERRORLEVEL%
