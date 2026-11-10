@echo off
setlocal
rem Q4_K_XL (Dynamic v3.1) sibling of the IQ4_XS launcher.
rem The existing supervisor discovers the READY model and synchronizes Claude/Codex context.
rem Measured on this box (benchmarks q4kxl-ab + buildtask 2026-11-10): decode/prefill are
rem slower than IQ4_XS on plain text, but the same 1M profile runs and the coding-agent
rem build task completed faster. Keep both launchers; pick per workload.
set "CONTEXT_TOKENS=262144"
set "CONTEXT_SUFFIX="
if defined STRATA_Q4KXL_CONTEXT if not "%STRATA_Q4KXL_CONTEXT%"=="1048576" (echo Unsupported context override.& exit /b 30)
if "%STRATA_Q4KXL_CONTEXT%"=="1048576" (
    set "CONTEXT_TOKENS=1048576"
    set "CONTEXT_SUFFIX=-1m"
)
set "DUAL_SUFFIX="
set "GPUS_ARGS="
if defined STRATA_Q4KXL_DUAL if not "%STRATA_Q4KXL_DUAL%"=="1" (echo Unsupported card override.& exit /b 34)
if "%STRATA_Q4KXL_DUAL%"=="1" (
    set "DUAL_SUFFIX=-2gpu"
    set "GPUS_ARGS=--gpus 0,1"
)
title Strata NVFP4 fork - Unsloth UD-Q4_K_XL - uncensored ON
set "STRATA_ROOT=%~dp0"
set "DATA_ROOT=%USERPROFILE%\Strata-data"
set "FORK_ROOT=%STRATA_ROOT%forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4"
set "ENGINE_DIR=%FORK_ROOT%\engine"
set "MODEL_DIR=%DATA_ROOT%\models\unsloth-UD-Q4_K_XL"
set "PACK_DIR=%DATA_ROOT%\packs\unsloth-ud-q4_k_xl"
set "MTP_DIR=%DATA_ROOT%\mtp\rt"
set "PROFILE_DIR=%LOCALAPPDATA%\Strata\profiles"
set "PROFILE=%PROFILE_DIR%\strata-unsloth-ud-q4_k_xl-nvfp4fork-uncensored-on%CONTEXT_SUFFIX%%DUAL_SUFFIX%.json"
set "PYTHON=%STRATA_ROOT%.venv\Scripts\python.exe"
set "PYTHONPATH=%STRATA_ROOT%tools;%PYTHONPATH%"
set "VECTOR=%FORK_ROOT%\data\uncensor\qwen-nvfp4-gptq-uncensored.gguf"
set "API_KEY_FILE=%USERPROFILE%\.config\strata\STRATA_API_KEY"

rem Match the existing IQ4 managed-launch opt-in. The supervisor discovers Q4_K_XL from
rem READY health and updates the existing Claude/Codex owners to this actual model/context.
if "%~1"=="" if not defined STRATA_SUPERVISOR_CHILD if exist "%USERPROFILE%\.config\strata\server-control\managed-launchers.enabled" (
    call "%~f0" --managed
    exit /b %ERRORLEVEL%
)
if /i "%~1"=="--managed" if not defined STRATA_SUPERVISOR_CHILD (
    "%PYTHON%" "%STRATA_ROOT%tools\strata_server_supervisor.py" --launcher "%~f0" --state-dir "%DATA_ROOT%\supervisor" --api-key-file "%API_KEY_FILE%" --token-file "%USERPROFILE%\.config\strata\server-control\restart-control.key" --fork-update-root "%STRATA_ROOT%." --sync-client-context --console-log --desktop-restart-config "%USERPROFILE%\.config\strata\server-control\desktop-restart.json"
    if errorlevel 1 (echo Managed Q4_K_XL failed. See the error above and %DATA_ROOT%\supervisor\server.log& pause& exit /b 1)
    exit /b
)
if not "%~1"=="" if /i not "%~1"=="--direct" if /i not "%~1"=="--managed" (echo Supported options: --direct, --managed& exit /b 2)

rem Resolve the exact same active bundle as the generated profile (no network here).
if exist "%STRATA_ROOT%.update\nvfp4-auto\active.json" (
    set "FORK_ROOT="
    for /f "delims=" %%F in ('""%PYTHON%" "%STRATA_ROOT%tools\strata_iq4xs_profiles.py" fork-root --strata-root "%STRATA_ROOT%.""') do set "FORK_ROOT=%%F"
    if not defined FORK_ROOT (echo Could not resolve the selected NVFP4 update.& pause& exit /b 29)
)
set "ENGINE_DIR=%FORK_ROOT%\engine"
set "VECTOR=%FORK_ROOT%\data\uncensor\qwen-nvfp4-gptq-uncensored.gguf"

if not exist "%API_KEY_FILE%" (echo Strata API key file is missing. Run INSTALL-STRATA-AGENT.bat --role server from the setup checkout.& pause& exit /b 21)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:USERPROFILE + '\.config\strata\STRATA_API_KEY'; $k=[IO.File]::ReadAllText($p); if ($k -cnotmatch '^[0-9a-fA-F]{64}$') { exit 1 }"
if errorlevel 1 (echo Strata API key file is malformed. No server was started.& pause& exit /b 22)
set "STRATA_API_KEY="
for /f "usebackq delims=" %%K in ("%API_KEY_FILE%") do set "STRATA_API_KEY=%%K"
if not defined STRATA_API_KEY (echo Strata API key file is empty. No server was started.& pause& exit /b 23)

set "STRATA_BIND_HOST=0.0.0.0"
if "%STRATA_SERVER_LOCAL_ONLY%"=="1" set "STRATA_BIND_HOST=127.0.0.1"
if "%STRATA_SERVER_LOCAL_ONLY%"=="1" goto strata_network_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=@(Get-NetConnectionProfile -ErrorAction Stop | Where-Object { $_.IPv4Connectivity -ne 'Disconnected' }); $f=@(Get-NetFirewallProfile -ErrorAction Stop); if (-not $p -or -not ($p | Where-Object NetworkCategory -eq 'Private') -or ($p | Where-Object NetworkCategory -eq 'Public') -or ($f | Where-Object { -not $_.Enabled })) { exit 1 }"
if errorlevel 1 (echo LAN startup requires an active Private network, no Public network, and Windows Firewall enabled for every profile.& pause& exit /b 24)
powershell -NoProfile -ExecutionPolicy Bypass -File "%STRATA_ROOT%tools\windows\check_strata_lan_firewall.ps1"
if errorlevel 1 (echo Port 8080 firewall scope is missing or too broad. Run tools\windows\allow_strata_lan.ps1 in an elevated PowerShell, then retry.& pause& exit /b 25)

:strata_network_ready
if not exist "%PYTHON%" (echo Strata Python environment is missing: "%PYTHON%"& pause& exit /b 2)
if not exist "%ENGINE_DIR%\strata.exe" (echo NVFP4 fork engine is missing.& pause& exit /b 3)
if not exist "%ENGINE_DIR%\strata-vision.exe" (echo NVFP4 fork vision engine is missing.& pause& exit /b 4)
if not exist "%FORK_ROOT%\release-manifest.json" (echo NVFP4 fork release manifest is missing.& pause& exit /b 5)
if not exist "%PACK_DIR%\index.txt" (echo Q4_K_XL native pack is missing. Rebuild it with tools\iq_pack.py --compat-bf16.& pause& exit /b 6)
if not exist "%PACK_DIR%\tokenizer\tokenizer.json" (echo Q4_K_XL tokenizer is missing.& pause& exit /b 7)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf" (echo Q4_K_XL v3.1 shard 1 is missing.& pause& exit /b 8)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-Q4_K_XL-00002-of-00004.gguf" (echo Q4_K_XL v3.1 shard 2 is missing.& pause& exit /b 9)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-Q4_K_XL-00003-of-00004.gguf" (echo Q4_K_XL v3.1 shard 3 is missing.& pause& exit /b 10)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-Q4_K_XL-00004-of-00004.gguf" (echo Q4_K_XL v3.1 PLE shard 4 is missing.& pause& exit /b 29)
if not exist "%STRATA_ROOT%data\expert-profile.bin" (echo Strata expert profile is missing.& pause& exit /b 11)
if not exist "%MTP_DIR%\dense.bin" (echo MTP dense file is missing.& pause& exit /b 12)
if not exist "%MTP_DIR%\experts.bin" (echo MTP experts file is missing.& pause& exit /b 13)
if not exist "%MTP_DIR%\draft_vocab.bin" (echo MTP draft vocabulary is missing.& pause& exit /b 14)
if not exist "%DATA_ROOT%\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf" (echo Vision projector is missing.& pause& exit /b 15)
if not exist "%VECTOR%" (echo NVFP4 fork refusal projection is missing.& pause& exit /b 16)

if not exist "%DATA_ROOT%\logs" mkdir "%DATA_ROOT%\logs"
if errorlevel 1 (echo Could not create the Strata log directory.& pause& exit /b 17)
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"
"%PYTHON%" "%STRATA_ROOT%tools\strata_iq4xs_profiles.py" render-profile --mode on --model q4_k_xl --strata-root "%STRATA_ROOT%." --data-root "%DATA_ROOT%" --output "%PROFILE%" --context %CONTEXT_TOKENS% %GPUS_ARGS%
if errorlevel 1 (echo Could not render the Q4_K_XL ON profile.& pause& exit /b 18)

"%PYTHON%" "%STRATA_ROOT%tools\patch_nvfp4_server_effort.py" "%FORK_ROOT%\serve\server.py"
if errorlevel 1 (echo Could not prepare Anthropic effort budgets.& pause& exit /b 26)

"%PYTHON%" "%STRATA_ROOT%tools\patch_nvfp4_vision_source_cache.py" "%FORK_ROOT%\serve\server.py"
if errorlevel 1 (echo Could not prepare image source cache.& pause& exit /b 28)

"%PYTHON%" "%STRATA_ROOT%tools\patch_nvfp4_response_guard.py" "%FORK_ROOT%\serve\server.py"
if errorlevel 1 (echo Could not prepare Messages response delivery.& pause& exit /b 27)

"%PYTHON%" "%STRATA_ROOT%tools\patch_nvfp4_cjk_ban.py" "%FORK_ROOT%\serve\server.py"
if errorlevel 1 (echo Could not prepare the CJK token ban.& pause& exit /b 32)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue; if ($c) { $c | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize; exit 1 } else { exit 0 }"
if errorlevel 1 (echo Port 8080 is occupied. Stop the running Strata server first; no process was stopped for you.& pause& exit /b 19)

cd /d "%FORK_ROOT%" || (echo Could not enter the NVFP4 fork directory.& pause& exit /b 20)
set "PATH=%ENGINE_DIR%;%PATH%"
echo Starting Unsloth UD-Q4_K_XL through the NVFP4 fork using the GPU selected in "%PROFILE%".
echo Managed mode synchronizes Claude/Codex after READY. Use --direct to bypass synchronization.
if "%STRATA_SERVER_LOCAL_ONLY%"=="1" echo Loopback API bind is enabled for local or SSH-tunnel clients.
if not "%STRATA_SERVER_LOCAL_ONLY%"=="1" echo LAN API bind is enabled; authentication is required. Use only a trusted Private network.
echo Uncensored mode is ON; the compatible refusal projection is loaded.
echo Context cap: %CONTEXT_TOKENS%. Start a new client session after switching context or model.
if "%CONTEXT_TOKENS%"=="1048576" echo 1M context uses dynamic RoPE: trained angles through 262K, then YaRN up to factor 4.
echo The IQ4_XS-trained expert profile is reused as the fork serve gate requires it (validated on Q4_K_XL).
echo Vision encoding uses CPU. The comparison sent no image.
if "%STRATA_Q4KXL_DUAL%"=="1" echo Two RTX 3090 Ti cards share the layers (layer split); the head runs on GPU 1.
"%PYTHON%" -m serve.server --engine strata --config "%PROFILE%" --host "%STRATA_BIND_HOST%" --port 8080 --image-max-tokens 1024
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (echo Strata fork server exited with code %EXIT_CODE%.& pause)
exit /b %EXIT_CODE%
