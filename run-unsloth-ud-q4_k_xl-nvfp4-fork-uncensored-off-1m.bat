@echo off
setlocal
rem Keep engine/model ownership in the Q4_K_XL base launcher; this wrapper only picks 1M.
set "STRATA_Q4KXL_CONTEXT=1048576"
call "%~dp0run-unsloth-ud-q4_k_xl-nvfp4-fork-uncensored-off.bat"
exit /b %ERRORLEVEL%
