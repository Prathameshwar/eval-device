@echo off
call "%~dp0start-llm.bat" --model qwenmedic-v1 %*
exit /b %ERRORLEVEL%
