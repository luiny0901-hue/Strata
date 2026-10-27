@echo off
setlocal
title Strata NVFP4 fork - Unsloth UD-IQ4_XS - uncensored OFF
set "STRATA_ROOT=%~dp0"
set "DATA_ROOT=%USERPROFILE%\Strata-data"
set "FORK_ROOT=%STRATA_ROOT%forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4"
set "ENGINE_DIR=%FORK_ROOT%\engine"
set "MODEL_DIR=%DATA_ROOT%\models\unsloth-UD-IQ4_XS"
set "PACK_DIR=%DATA_ROOT%\packs\unsloth-ud-iq4_xs"
set "MTP_DIR=%DATA_ROOT%\mtp\rt"
set "PROFILE_DIR=%LOCALAPPDATA%\Strata\profiles"
set "PROFILE=%PROFILE_DIR%\strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-off.json"
set "PYTHON=%STRATA_ROOT%.venv\Scripts\python.exe"
set "VECTOR=%FORK_ROOT%\data\uncensor\qwen-nvfp4-gptq-uncensored.gguf"
set "API_KEY_FILE=%USERPROFILE%\.config\strata\STRATA_API_KEY"

if "%~1"=="" if not defined STRATA_SUPERVISOR_CHILD if exist "%USERPROFILE%\.config\strata\server-control\managed-launchers.enabled" (
    call "%~f0" --managed
    exit /b
)

if /i "%~1"=="--managed" if not defined STRATA_SUPERVISOR_CHILD (
    "%PYTHON%" "%STRATA_ROOT%tools\strata_server_supervisor.py" --launcher "%~f0" --state-dir "%DATA_ROOT%\supervisor" --api-key-file "%API_KEY_FILE%" --token-file "%USERPROFILE%\.config\strata\server-control\restart-control.key" --console-log --desktop-restart-config "%USERPROFILE%\.config\strata\server-control\desktop-restart.json"
    if errorlevel 1 (
        echo Managed Strata failed. See the error above and %DATA_ROOT%\supervisor\server.log
        pause
        exit /b 1
    )
    exit /b
)

if not exist "%API_KEY_FILE%" (echo Strata API key file is missing. Run configure_strata_api_key.ps1 -Generate from the setup checkout.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 21)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:USERPROFILE + '\.config\strata\STRATA_API_KEY'; $k=[IO.File]::ReadAllText($p); if ($k -cnotmatch '^[0-9a-fA-F]{64}$') { exit 1 }"
if errorlevel 1 (echo Strata API key file is malformed. No server was started.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 22)
set "STRATA_API_KEY="
for /f "usebackq delims=" %%K in ("%API_KEY_FILE%") do set "STRATA_API_KEY=%%K"
if not defined STRATA_API_KEY (echo Strata API key file is empty. No server was started.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 23)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=@(Get-NetConnectionProfile -ErrorAction Stop | Where-Object { $_.IPv4Connectivity -ne 'Disconnected' }); $f=@(Get-NetFirewallProfile -ErrorAction Stop); if (-not $p -or -not ($p | Where-Object NetworkCategory -eq 'Private') -or ($p | Where-Object NetworkCategory -eq 'Public') -or ($f | Where-Object { -not $_.Enabled })) { exit 1 }"
if errorlevel 1 (echo LAN startup requires an active Private network, no Public network, and Windows Firewall enabled for every profile.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 24)
powershell -NoProfile -ExecutionPolicy Bypass -File "%STRATA_ROOT%tools\windows\check_strata_lan_firewall.ps1"
if errorlevel 1 (echo Port 8080 firewall scope is missing or too broad. Run tools\windows\allow_strata_lan.ps1 in an elevated PowerShell, then retry.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 25)

if not exist "%PYTHON%" (echo Strata Python environment is missing: "%PYTHON%"& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 2)
if not exist "%ENGINE_DIR%\strata.exe" (echo NVFP4 fork engine is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 3)
if not exist "%ENGINE_DIR%\strata-vision.exe" (echo NVFP4 fork vision engine is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 4)
if not exist "%FORK_ROOT%\release-manifest.json" (echo NVFP4 fork release manifest is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 5)
if not exist "%PACK_DIR%\index.txt" (echo IQ4_XS native pack is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 6)
if not exist "%PACK_DIR%\tokenizer\tokenizer.json" (echo IQ4_XS tokenizer is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 7)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf" (echo IQ4_XS shard 1 is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 8)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf" (echo IQ4_XS PLE shard 2 is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 9)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf" (echo IQ4_XS shard 3 is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 10)
if not exist "%STRATA_ROOT%data\expert-profile.bin" (echo Strata expert profile is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 11)
if not exist "%MTP_DIR%\dense.bin" (echo MTP dense file is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 12)
if not exist "%MTP_DIR%\experts.bin" (echo MTP experts file is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 13)
if not exist "%MTP_DIR%\draft_vocab.bin" (echo MTP draft vocabulary is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 14)
if not exist "%DATA_ROOT%\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf" (echo Vision projector is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 15)
if not exist "%VECTOR%" (echo NVFP4 fork refusal projection is missing.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 16)

if not exist "%DATA_ROOT%\logs" mkdir "%DATA_ROOT%\logs"
if errorlevel 1 (echo Could not create the Strata log directory.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 17)
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"
"%PYTHON%" "%STRATA_ROOT%tools\strata_iq4xs_profiles.py" render-profile --mode off --strata-root "%STRATA_ROOT%." --data-root "%DATA_ROOT%" --output "%PROFILE%"
if errorlevel 1 (echo Could not render the OFF profile.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 18)

"%PYTHON%" "%STRATA_ROOT%tools\patch_nvfp4_response_guard.py" "%FORK_ROOT%\serve\server.py"
if errorlevel 1 (echo Could not prepare Messages response delivery.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 27)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue; if ($c) { $c | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize; exit 1 } else { exit 0 }"
if errorlevel 1 (echo Port 8080 is occupied or could not be checked. No process was stopped.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 19)

cd /d "%FORK_ROOT%" || (echo Could not enter the NVFP4 fork directory.& if not defined STRATA_SUPERVISOR_CHILD pause& exit /b 20)
set "PATH=%ENGINE_DIR%;%PATH%"
echo Starting Unsloth UD-IQ4_XS through the NVFP4 fork on RTX 3090 Ti GPU 1.
echo LAN API bind is enabled; authentication is required. Use only a trusted Private network.
echo If remote clients are blocked, install the Private/LocalSubnet rule from the setup checkout's tools\windows\allow_strata_lan.ps1.
echo Uncensored mode is OFF; the compatible refusal projection is loaded.
echo Context cap: 262144. Full 262K context stress was not verified.
echo Vision encoding uses CPU. The comparison sent no image.
"%PYTHON%" -m serve.server --engine strata --config "%PROFILE%" --host 0.0.0.0 --port 8080 --image-max-tokens 1024
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (echo Strata fork server exited with code %EXIT_CODE%.& if not defined STRATA_SUPERVISOR_CHILD pause)
exit /b %EXIT_CODE%
