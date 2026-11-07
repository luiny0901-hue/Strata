@echo off
setlocal
rem Layer split of both RTX 3090 Ti cards (GPU 1 runs the head last); this launcher supervises itself
rem so switching back to a single card starts a fresh supervisor instead of restarting this profile.
set "STRATA_IQ4XS_DUAL=1"
set "STRATA_ARENA_PIN_GIB=20"
if not "%~1"=="" if /i not "%~1"=="--managed" (echo Supported option: --managed& exit /b 2)
set "STRATA_ROOT=%~dp0"
set "DATA_ROOT=%USERPROFILE%\Strata-data"
set "PYTHON=%STRATA_ROOT%.venv\Scripts\python.exe"
set "API_KEY_FILE=%USERPROFILE%\.config\strata\STRATA_API_KEY"
if not defined STRATA_SUPERVISOR_CHILD goto strata_dual_supervise
call "%~dp0run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.bat" --managed
exit /b %ERRORLEVEL%
:strata_dual_supervise
"%PYTHON%" "%STRATA_ROOT%tools\strata_server_supervisor.py" --launcher "%~f0" --state-dir "%DATA_ROOT%\supervisor" --api-key-file "%API_KEY_FILE%" --token-file "%USERPROFILE%\.config\strata\server-control\restart-control.key" --fork-update-root "%STRATA_ROOT%." --sync-client-context --console-log --desktop-restart-config "%USERPROFILE%\.config\strata\server-control\desktop-restart.json"
if errorlevel 1 (
    echo Managed Strata failed. See the error above and %DATA_ROOT%\supervisor\server.log
    pause
    exit /b 1
)
exit /b 0
