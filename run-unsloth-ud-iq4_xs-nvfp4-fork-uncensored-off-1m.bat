@echo off
setlocal
rem Keep engine/model/maintenance ownership in the existing launcher.
set "STRATA_IQ4XS_CONTEXT=1048576"
if not "%~1"=="" if /i not "%~1"=="--managed" (echo Supported option: --managed& exit /b 2)
call "%~dp0run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-off.bat" --managed
exit /b %ERRORLEVEL%
