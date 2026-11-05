@echo off
setlocal
set "PYTHONUTF8=1"
python -X utf8 "%~dp0manage_local_models.py" %*
set "MODELS_UI_EXIT=%ERRORLEVEL%"
if not "%MODELS_UI_EXIT%"=="0" pause
exit /b %MODELS_UI_EXIT%
