@echo off
setlocal
if not "%~1"=="" goto dispatch
call "%~f0" setup
set "setup_exit=%ERRORLEVEL%"
pause
exit /b %setup_exit%
:dispatch
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if not errorlevel 1 goto use_python
echo Python 3 is required. Install Python for this user, then run this file again.
exit /b 2
:use_py
py -3 "%~dp0setup_client.py" %*
exit /b %ERRORLEVEL%
:use_python
python "%~dp0setup_client.py" %*
exit /b %ERRORLEVEL%
