@echo off
call "%~dp0tools\remote_agent_client\setup-windows.bat" %*
exit /b %ERRORLEVEL%
