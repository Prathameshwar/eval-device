@echo off
call "%~dp0setup.bat" --model qwen3.5-4b %*
exit /b %ERRORLEVEL%
