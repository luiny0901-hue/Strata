@echo off
setlocal
chcp 65001 >nul
title Strata - 통합 설치
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install-agent.ps1" %*
set "STRATA_INSTALL_RESULT=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %STRATA_INSTALL_RESULT%
