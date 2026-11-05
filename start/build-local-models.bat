@echo off
setlocal
set "MODELS_BUILD_PYTHON=%~dp0..\local-models\.venv\Scripts\python.exe"
if not exist "%MODELS_BUILD_PYTHON%" (
  echo Local Models build environment is missing. Create local-models\.venv with Python 3.12 first.
  exit /b 1
)
"%MODELS_BUILD_PYTHON%" -X utf8 "%~dp0build_local_models.py" %* 2>&1
exit /b %ERRORLEVEL%
