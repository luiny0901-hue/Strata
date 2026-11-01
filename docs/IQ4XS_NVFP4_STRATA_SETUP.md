# NVFP4 fork + Unsloth UD-IQ4_XS Strata 서버 복원

이 안내는 Windows Strata 서버의 모델·팩·엔진 복원과 ON/OFF 프로필 준비만 다룹니다. Claude Desktop Code 연결은 [Claude 연결 안내](CLAUDE_OPENCODEX_KO.md)를 따릅니다.

## Windows 초기화 뒤 복원

1. Strata 저장소와 Python 환경을 [AI 설치 안내](AI_SETUP.md)에 따라 준비합니다. 비공개 작업 변경과 실행기 템플릿을 복원하고 기존 모델 데이터는 백업에서 따로 가져옵니다.
2. 기록된 NVFP4 fork 빌드를 저장소의 `FORK_RELATIVE` 경로에 복원합니다. 저장소의 `tools/strata_iq4xs_profiles.py`가 요구하는 `release-manifest.json`과 엔진 파일이 있어야 합니다.
3. 저장소가 제공하는 SHA-256 검증 패치를 적용합니다.

   ```powershell
   & .\tools\apply_nvfp4_vision_pipe_fix.ps1
   ```

   이 패치는 검토된 fork 파일 해시만 허용합니다. 다른 fork 버전이면 적용하지 말고 먼저 해당 버전의 변경을 검토합니다.

4. UD-IQ4_XS 모델 샤드, Strata pack, MTP, 비전 projector와 expert profile을 사용자 데이터 폴더에 복원합니다. 빠진 파일은 [ORCA 안내](ORCA.md)와 [아티팩트 매니페스트](reports/2026-10-17-iq4xs-artifact-manifest.json)에서 확인합니다. 모델 가중치와 fork 바이너리는 저장소에 포함되지 않습니다.
5. 파일을 새로 내려받았거나 복원했으면 SHA-256 매니페스트로 확인합니다. 이 명령은 대형 모델 파일 전체를 읽으며 수 분 걸릴 수 있습니다.

   ```powershell
   & .\.venv\Scripts\python.exe .\tools\strata_iq4xs_profiles.py verify-assets
   ```

6. ON/OFF 프로필 템플릿과 실행기를 점검합니다.

   ```powershell
   & .\.venv\Scripts\python.exe .\tools\strata_iq4xs_profiles.py validate-templates
   & .\.venv\Scripts\python.exe .\tools\test_strata_iq4xs_profiles.py
   ```

7. 필요할 때 `run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.bat` 또는 `...-off.bat`를 실행합니다. 포트 8080이 이미 사용 중이면 기존 프로세스를 종료하지 말고 먼저 소유자를 확인합니다. ON/OFF 전환 전 현재 서버를 정상 종료합니다.

## 모델·프로필 범위

실행기는 `profiles/strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-{on,off}.json.template`에서 프로필을 생성합니다. 템플릿이 현재 VRAM reserve, 컨텍스트, 샘플링과 모델 경로의 정본입니다. 실행 중인 서버를 바꾸기 전에 템플릿과 실제 생성 JSON을 비교합니다. 이 안내에서 특정 토큰 속도나 전체 262K 부하 성공을 보장하지 않습니다.

## 보존된 과거 측정

`docs/reports/`의 OpenCode 측정 보고서와 영수증은 당시 요청·서버의 역사 기록으로 유지합니다. 현재 Claude Desktop Code 경로의 성능 측정으로 해석하지 않습니다.
