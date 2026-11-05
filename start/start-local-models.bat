@echo off
setlocal
set "MODELS_LAUNCHER=%~dp0..\local-models\manage-local-models.bat"
if not exist "%MODELS_LAUNCHER%" (
  echo [ERROR] Manage Local Models launcher is missing.
  echo Keep the start and local-models folders together in the project directory.
  if /I not "%~1"=="--help" pause
  exit /b 1
)
call "%MODELS_LAUNCHER%" %*
exit /b %ERRORLEVEL%
