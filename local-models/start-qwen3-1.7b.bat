@echo off
call "%~dp0start-llm.bat" --model qwen3-1.7b %*
exit /b %ERRORLEVEL%
