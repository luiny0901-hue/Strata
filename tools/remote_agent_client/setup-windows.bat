@echo off
setlocal
:dispatch
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap-windows.ps1" %*
exit /b %ERRORLEVEL%
