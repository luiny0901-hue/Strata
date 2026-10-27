@echo off
setlocal
set "PYTHONUTF8=1"
if not defined STRATA_CLAUDE_PYTHON if exist "%~dp0.venv\Scripts\python.exe" set "STRATA_CLAUDE_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined STRATA_CLAUDE_PYTHON if exist "%USERPROFILE%\Strata\.venv\Scripts\python.exe" set "STRATA_CLAUDE_PYTHON=%USERPROFILE%\Strata\.venv\Scripts\python.exe"
if not defined STRATA_CLAUDE_PYTHON set "STRATA_CLAUDE_PYTHON=python"
"%STRATA_CLAUDE_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 실행 파일을 찾지 못했습니다.
  echo Claude Desktop Code 연결 설정을 먼저 마치거나 STRATA_CLAUDE_PYTHON을 지정하세요.
  exit /b 9009
)
if /I "%~1"=="doctor" goto doctor
if /I "%~1"=="desktop-restart" goto desktop_restart
"%STRATA_CLAUDE_PYTHON%" "%~dp0tools\claude_opencodex_client.py" setup %*
set "STRATA_CLAUDE_RESULT=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %STRATA_CLAUDE_RESULT%

:desktop_restart
"%STRATA_CLAUDE_PYTHON%" "%~dp0tools\claude_desktop_runtime.py" configure
set "STRATA_CLAUDE_RESULT=%ERRORLEVEL%"
pause
exit /b %STRATA_CLAUDE_RESULT%

:doctor
"%STRATA_CLAUDE_PYTHON%" "%~dp0tools\claude_opencodex_client.py" doctor
set "STRATA_CLAUDE_RESULT=%ERRORLEVEL%"
pause
exit /b %STRATA_CLAUDE_RESULT%
