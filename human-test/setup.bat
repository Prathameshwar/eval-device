@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
pushd "%~dp0"
uv sync --frozen --no-dev
set "HUMAN_EXIT=%ERRORLEVEL%"
if not "%HUMAN_EXIT%"=="0" goto done
"%~dp0.venv\Scripts\python.exe" -c "import tkinter; import sounddevice; import cv2; import av; import local_model_client; print('Desktop, microphone, inference client and camera dependencies ready')"
set "HUMAN_EXIT=%ERRORLEVEL%"
if not "%HUMAN_EXIT%"=="0" goto done
:done
popd
if not "%HUMAN_EXIT%"=="0" pause
exit /b %HUMAN_EXIT%
