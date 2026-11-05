@echo off
setlocal
"%~dp0..\..\..\platform\api\.venv\Scripts\python.exe" -X utf8 "%~dp0launch_test.py" %*
exit /b %ERRORLEVEL%
