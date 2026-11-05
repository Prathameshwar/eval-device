@echo off
call "%~dp0setup.bat" --model qwenmedic-v1 %*
exit /b %ERRORLEVEL%
