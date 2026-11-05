@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
if not exist "%~dp0..\api\.venv\Scripts\pms-admin.exe" (
  echo Install the platform API environment with uv sync first.
  exit /b 1
)
pushd "%~dp0..\api"
if errorlevel 1 exit /b 1
".venv\Scripts\pms-admin.exe" init-database %*
set "PMS_INIT_EXIT=%ERRORLEVEL%"
popd
exit /b %PMS_INIT_EXIT%
