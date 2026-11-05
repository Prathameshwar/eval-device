@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
if not exist "%~dp0.venv-medical\Scripts\python.exe" (
  uv venv --python 3.12 "%~dp0.venv-medical"
  if errorlevel 1 goto failed
)
uv pip install --python "%~dp0.venv-medical\Scripts\python.exe" -r "%~dp0requirements-medical.txt"
if errorlevel 1 goto failed
"%~dp0.venv-medical\Scripts\python.exe" -X utf8 "%~dp0scripts\install_medical.py"
if errorlevel 1 goto failed
exit /b 0
:failed
 echo Medical setup failed. Existing audio models and runtime were preserved.
exit /b 1
