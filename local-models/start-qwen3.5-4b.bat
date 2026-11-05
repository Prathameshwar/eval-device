@echo off
call "%~dp0start-llm.bat" --model qwen3.5-4b %*
exit /b %ERRORLEVEL%
