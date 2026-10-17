@echo off
setlocal
title Strata NVFP4 fork - Unsloth UD-IQ4_XS - uncensored ON
set "STRATA_ROOT=%~dp0"
set "DATA_ROOT=%USERPROFILE%\Strata-data"
set "FORK_ROOT=%STRATA_ROOT%forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4"
set "ENGINE_DIR=%FORK_ROOT%\engine"
set "MODEL_DIR=%DATA_ROOT%\models\unsloth-UD-IQ4_XS"
set "PACK_DIR=%DATA_ROOT%\packs\unsloth-ud-iq4_xs"
set "MTP_DIR=%DATA_ROOT%\mtp\rt"
set "PROFILE_DIR=%LOCALAPPDATA%\Strata\profiles"
set "PROFILE=%PROFILE_DIR%\strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-on.json"
set "PYTHON=%STRATA_ROOT%.venv\Scripts\python.exe"
set "VECTOR=%FORK_ROOT%\data\uncensor\qwen-nvfp4-gptq-uncensored.gguf"

if not exist "%PYTHON%" (echo Strata Python environment is missing: "%PYTHON%"& pause& exit /b 2)
if not exist "%ENGINE_DIR%\strata.exe" (echo NVFP4 fork engine is missing.& pause& exit /b 3)
if not exist "%ENGINE_DIR%\strata-vision.exe" (echo NVFP4 fork vision engine is missing.& pause& exit /b 4)
if not exist "%FORK_ROOT%\release-manifest.json" (echo NVFP4 fork release manifest is missing.& pause& exit /b 5)
if not exist "%PACK_DIR%\index.txt" (echo IQ4_XS native pack is missing.& pause& exit /b 6)
if not exist "%PACK_DIR%\tokenizer\tokenizer.json" (echo IQ4_XS tokenizer is missing.& pause& exit /b 7)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf" (echo IQ4_XS shard 1 is missing.& pause& exit /b 8)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf" (echo IQ4_XS PLE shard 2 is missing.& pause& exit /b 9)
if not exist "%MODEL_DIR%\Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf" (echo IQ4_XS shard 3 is missing.& pause& exit /b 10)
if not exist "%STRATA_ROOT%data\expert-profile.bin" (echo Strata expert profile is missing.& pause& exit /b 11)
if not exist "%MTP_DIR%\dense.bin" (echo MTP dense file is missing.& pause& exit /b 12)
if not exist "%MTP_DIR%\experts.bin" (echo MTP experts file is missing.& pause& exit /b 13)
if not exist "%MTP_DIR%\draft_vocab.bin" (echo MTP draft vocabulary is missing.& pause& exit /b 14)
if not exist "%DATA_ROOT%\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf" (echo Vision projector is missing.& pause& exit /b 15)
if not exist "%VECTOR%" (echo NVFP4 fork refusal projection is missing.& pause& exit /b 16)

if not exist "%DATA_ROOT%\logs" mkdir "%DATA_ROOT%\logs"
if errorlevel 1 (echo Could not create the Strata log directory.& pause& exit /b 17)
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"
"%PYTHON%" "%STRATA_ROOT%tools\iq4xs_opencode_setup.py" render-profile --mode on --strata-root "%STRATA_ROOT%." --data-root "%DATA_ROOT%" --output "%PROFILE%"
if errorlevel 1 (echo Could not render the ON profile.& pause& exit /b 18)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue; if ($c) { $c | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize; exit 1 } else { exit 0 }"
if errorlevel 1 (echo Port 8080 is occupied or could not be checked. No process was stopped.& pause& exit /b 19)

cd /d "%FORK_ROOT%" || (echo Could not enter the NVFP4 fork directory.& pause& exit /b 20)
set "PATH=%ENGINE_DIR%;%PATH%"
echo Starting Unsloth UD-IQ4_XS through the NVFP4 fork on RTX 3090 Ti GPU 1.
echo Uncensored mode is ON; the compatible refusal projection is loaded.
echo Context cap: 262144. Full 262K context stress was not verified.
echo Vision encoder defaults to CPU. See docs/reports/2026-10-17-iq4xs-vision-cpu-gpu-comparison.md
"%PYTHON%" -m serve.server --engine strata --config "%PROFILE%" --host 127.0.0.1 --port 8080 --image-max-tokens 1024
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (echo Strata fork server exited with code %EXIT_CODE%.& pause)
exit /b %EXIT_CODE%
