# NVFP4 포크 안정판 자동 업데이트

현재 ON/OFF 실행기가 사용하는 `sergqwer/strata-nvfp4`의 Windows x64 배포만 대상으로 한다. 기본은 꺼져 있으며 `SETUP-STRATA-UPDATES.bat`에서 켜기·끄기·상태 확인을 선택한다. 켜기는 기존 관리 실행기도 활성화한다. 실행 중인 서버를 중단하거나 다른 프로세스를 인수하지 않는다. 새 확인기는 다음 서버 시작부터 동작한다.

## 동작

1. 기존 supervisor가 서버 준비를 확인한 뒤 별도 스레드에서 하루 한 번 공식 GitHub 배포 목록을 확인한다. 실패도 하루 동안 캐시한다. 요청·토큰마다 조회하거나 별도 서비스·예약 작업을 만들지 않는다.
2. GitHub의 draft/prerelease 표시와 버전 이름을 함께 확인한다. `beta`·`alpha`·`rc` 등 안정판 형식에 맞지 않는 태그는 정식 배포로 표시돼 있어도 제외한다. 다른 Strata 저장소나 `strata-windows-x64.zip`은 선택하지 않는다.
3. 새 안정판이 있으면 포크 전용 ZIP의 정확한 URL·크기·GitHub SHA-256을 검증하고 별도 폴더에 준비한다. 경로 이탈·링크·Windows 경로 별칭·중복 경로·과도한 압축 해제를 거부한다. 사용자 API 키를 GitHub에 보내지 않는다.
4. 현재 배포 manifest를 기준으로 로컬 수정과 추가 Python 서버 모듈을 보존한다. 해당 파일의 원본이 새 버전에서 바뀌었거나 Python 의존성이 달라지면 자동 병합·pip 설치를 하지 않고 보류한다. 기존 추론·비전·응답 처리 훅의 통합 지점도 검사한다. 모델·Pack·프로필 템플릿은 바꾸지 않는다.
5. 준비된 버전은 **다음 supervisor 최초 시작**에서만 적용한다. 가동 중의 일반 재시작 요청이나 슬롯이 잠시 빈 순간에는 적용하지 않는다. 따라서 도구 사용 중이나 프록시 대기열에 요청이 있는 상황을 잘못 유휴로 판단해 작업을 끊지 않는다.
6. 적용 전후 파일 해시를 다시 확인하고 기존 폴더를 보존한다. ON/OFF 실행기와 프로필 생성기는 같은 선택 포인터를 읽는다. 기존 supervisor의 인증된 health·모델 준비 확인이 실패하면 후보 프로세스 트리를 정리하고 포트 해제를 확인한 뒤 이전 버전을 한 번 기동한다. 후보 기동 도중 PC가 꺼졌다면 다음 시작에서 이전 선택을 복원한다. 실패한 버전은 자동 재시도하지 않는다. 작업·대화·도구 요청을 재전송하지 않는다.

새 버전의 일반적인 호환성을 보장하지 않는다. 변경된 의존성·로컬 수정 충돌·새 배포 구조는 검토가 필요한 유지보수로 남긴다. 모델 추론이나 실제 Code 대화 시험 없이 성능 향상·품질 동등성을 보장하지 않는다. Linux는 현재 Windows 바이너리를 설치하지 않으며, 새 안정판 확인 결과를 `platform_unavailable`로 남긴다. 이 기능은 포크 엔진·서버 업데이트이며 유지보수 저장소 소스, OpenCodex, Claude Desktop, 모델·Pack을 함께 업데이트하지 않는다.

## 상태와 되돌림

실제 서버 루트의 `.update/nvfp4-auto/` 아래에 `config.json`, `status.json`, `pending.json`, `active.json`, `transaction.json`, `rejected.json`이 저장된다. API 키·대화는 저장하지 않는다. `prepared`는 다운로드·호환성 준비 완료이며 실행 검증 완료가 아니다. `updated`는 현재 모델의 기동 준비 확인까지 통과했다는 뜻이다. `deferred`·`rejected`는 기존 버전을 유지하며 기록의 이유를 확인해야 한다.

끄기는 이후 조회·새 적용을 끈다. 이미 정상 적용된 버전을 강제로 내리지 않는다. 이전 폴더는 자동 삭제하지 않으므로 장기 운영 시 용량을 확인한다. 실패 영수증을 지워 같은 버전을 무조건 재시도하지 말고 원인을 검토한다.

터미널에서 상태를 확인하려면 실제 설치 경로에 맞춰 실행한다.

```powershell
C:\Users\luiny\Strata\.venv\Scripts\python.exe -B -X utf8 C:\Users\luiny\Strata\tools\strata_fork_update.py --strata-root C:\Users\luiny\Strata status
```

## 검증 범위

`tools.test_strata_fork_update`, 기존 supervisor·관리 실행기·프로필 검사를 재사용한다. CPU/모의 검사는 안정판 선택, 잘못된 ZIP·해시 거부, 변경 충돌 보류, 기동 실패·중단 복구 및 실행 중 무재시작 계약을 확인한다. 실제 새 안정판 다운로드·GPU 기동·새 PC 설치 성공의 근거와 구분한다.

### 2026-10-29 로컬 적용 기록

- 첫 sandbox 검사들은 Windows 임시 폴더 쓰기 권한 때문에 실행 환경 단계에서 실패했다. 실제 권한으로 재실행한 44개 검사에서는 ZIP 역슬래시 경로 항목 1개가 실패했다. 첫 테스트 입력 보정 후 17개 재검사에서도 같은 항목이 실패해, 읽는 쪽에서 ZipInfo가 경로를 정규화하는 것을 확인했다. `orig_filename`을 검증하도록 보완한 뒤 관련 17개와 실제 CMD 선택 검사 1개가 통과했다.
- 최종 명령: `.venv\Scripts\python.exe -B -X utf8 -m unittest tools.test_strata_fork_update tools.test_strata_iq4xs_profiles.ProfileTemplateTests tools.test_strata_iq4xs_profiles.LauncherImageBudgetTests tools.test_managed_launcher_optin tools.test_strata_server_supervisor -q`. 47개, 16.513초, 통과. 새 검사 중 후보 기동·원복은 모의 객체이며 기존 supervisor 검사는 임시 CPU HTTP 서버와 소유 프로세스를 사용한다. 실제 GPU나 운영 서버 기동 시험이 아니다.
- 실제 서버 루트에 기능을 백업 후 배치하고 `enabled: true`, `stable`, `next_owner_start`를 저장했다. 공식 GitHub 목록의 최초 확인 결과 설치 `0.1.44.1-nvfp4.2`와 최신 안정판 `v0.1.44.1-nvfp4.2`가 같아 `current`다. 베타는 제외했으며 ZIP 다운로드·모델 시작·운영 서버 재시작은 하지 않았다.
- 이미 실행 중인 supervisor는 메모리에 이전 코드를 유지한다. 다음 ON/OFF 서버 실행에서 새 확인기가 시작된다. 실제 미래 안정판의 다운로드·GPU 기동·성능·Code 대화 복구는 아직 검증하지 않았다.

- 실제 `SETUP-STRATA-UPDATES.bat status` 첫 실행은 LF 줄바꿈 때문에 CMD 명령 해석 오류가 났다. 프로세스 종료 코드가 0이었어도 실패로 판정했다. 소스·설치본을 CRLF로 보완한 뒤 재실행에서 오류 없이 `enabled: true`, `current`와 기존 포크 경로가 표시됐다.
