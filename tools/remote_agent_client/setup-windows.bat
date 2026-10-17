@echo off
setlocal
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
