@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONUTF8=1"
python -X utf8 "%~dp0build_platform.py"
exit /b %ERRORLEVEL%
