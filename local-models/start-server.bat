@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
python -X utf8 "%~dp0scripts\run.py" --server %*
set "LLM_EXIT=%ERRORLEVEL%"
if not "%LLM_EXIT%"=="0" pause
exit /b %LLM_EXIT%
