@echo off
call "%~dp0setup.bat" --model qwen3-1.7b %*
exit /b %ERRORLEVEL%
