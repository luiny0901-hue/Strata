@echo off
setlocal
chcp 65001 >nul
set "SERVER_ROOT=%~dp0"
if not exist "%SERVER_ROOT%forks\sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2\strata-nvfp4\release-manifest.json" set "SERVER_ROOT=%USERPROFILE%\Strata\"
set "PYTHON=%SERVER_ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (echo 기존 Strata 서버 설치를 찾지 못했습니다.& pause& exit /b 2)
set "ACTION=%~1"
if defined ACTION goto selected
echo Strata 안정판 자동 업데이트
echo 1. 켜기: 하루 한 번 확인, 준비된 버전은 다음 서버 시작 때 적용
echo 2. 끄기: 현재 버전 유지
echo 3. 상태 확인
choice /c 123 /n /m "번호를 선택하세요: "
if errorlevel 3 (set "ACTION=status"& goto selected)
if errorlevel 2 (set "ACTION=disable"& goto selected)
set "ACTION=enable"
:selected
"%PYTHON%" -B -X utf8 "%~dp0tools\strata_fork_update.py" --strata-root "%SERVER_ROOT%." "%ACTION%"
if errorlevel 1 (echo 설정을 완료하지 못했습니다. 위 오류를 확인하세요.& pause& exit /b 1)
echo 변경된 확인기는 다음 서버 실행부터 동작합니다. 작업 중 서버를 중단하지 않습니다.
if "%~1"=="" pause
