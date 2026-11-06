# OpenCodex PID 재사용 스테일 판정 (2026-11-06)

## 증상과 원인

Strata 기동 시 콘솔에 `Strata is ready, but client context synchronization failed.`가 뜨고 클라이언트 동기화가 실패했다. 사슬은 이렇다.

1. Windows 재부팅 과정에서 OpenCodex가 기록한 PID(9616)를 OS가 다른 프로세스(NgcIso.exe, 생성 시각 2026-11-06 13:05:07)에 재사용했다.
2. OpenCodex 2.95.0의 소유권 검증은 그 PID의 명령줄을 읽을 수 없어 기존 실행자가 살아 있는지 죽었는지 확신하지 못했고, `Proxy ownership is unverified; startup refused.`로 게이트웨이(127.0.0.1:10100) 기동을 반복 거부했다. Recovery Journal의 과거 PID(34532) 기록은 그대로 보존됐다.
3. Strata supervisor의 READY 후 클라이언트 동기화는 10100의 `/healthz`를 쓰기 때문에 연결 거부(WinError 10061)로 실패했다. Strata와 supervisor는 정상았고, 끝단 증상만 로그에 남았다.

조치는 사람이 했다: 서비스 중지 → `ocx.pid`를 삭제하지 않고 백업 이름으로 이동 → 서비스 재시작. Journal과 설정은 보존됐고 10100이 떠서 동기화도 복구됐다(동기화 영수증 `synchronized`, 13:32:20).

## 로컬 유지보수 패치

`tools/patch_opencodex_pid_reuse.py`가 검증한 `@bitkyc08/opencodex` 2.95.0 설치에만 마커 `STRATA_OPENCODEX_PID_REUSE_V1`로 다음을 추가한다. 다른 버전·알 수 없는 소스 구조는 거부하고 재적용은 무변경이며 백업은 설치 안의 `.strata-pid-reuse`에 남는다.

- `src/config/process-state.ts`: PID 프로세스의 생성 시각을 WMIC(`Win32_Process.CreationDate`)으로 읽고 실패 시 고정 신뢰 PowerShell CIM으로 읽는 헬퍼와, 그 시각이 PID 기록 파일의 mtime보다 5초 늦으면 "기록 이후 재사용"으로 확증하는 `pidReusedSincePidRecord`을 추가한다. 시각을 읽을 수 없으면 지금까지와 똑같이 확신 불가(보수적 거부)로 남는다.
- `src/cli/start-owner-fence.ts`: 기동 퍼티가 `absent`가 아닌 상태를 만나면 기존 동작(영구 거부) 전에 재사용 여부를 확인하고, 확증되면 absent와 같은 복구(PID 기록 정리 후 재조정)로 이어간다. 재사용이 아니면 메시지와 동작이 전부 그대로다.

의도는 이 사고의 두 조건(재부팅 후 PID 재사용 + 명령줄 봉쇄)이 겹쳤을 때만 판정이 발동하도록 좁히는 것이다. 실제 실행 중인 프록시는 PID 기록을 자기가 실행 중에 쓰므로 생성 시각이 기록보다 늦을 수 없고, 시계 역주행과 기타 플랫폼은 기존 동작을 유지한다.

## 확인

- `py -m tools.test_patch_opencodex_pid_reuse`: 4개 통과(적용·멱등 재적용·일부 상태/중복 앵커 거부·BOM/CRLF 보존과 버전 경계).
- 설치본 적용: 2개 파일 변경, 재적용 무변경(백업 영수증 `.strata-pid-reuse/backups/…` 존재).
- 런타임(번들 Bun, 읽기 전용, 서비스 재시작 없음): 실제 소유 PID(4480)는 재사용 아님(`false`), 방금 만든 무관 프로세스는 재사용(`true`), 자기 프로세스 생성 시각 오차 0.3초. 즉 정상 기동은 이전과 동일하고 이번 사고 상태만 스테일로 판정된다.
- 반영 시점: 퍼티는 프록시 기동 때 도는 코드이므로 다음 기동(서비스 재시작·재부팅)부터 적용된다. 규칙에 따라 불필요한 재시작은 하지 않았다.

npm 업데이트 후에는 기존 패치들과 같이 버전·소스를 다시 검증해야 한다(패치 도구가 2.95.0 외에는 거부). 이 PC의 유지보수 패치이며 공식 OpenCodex 배포에 포함된 수정이 아니다.
