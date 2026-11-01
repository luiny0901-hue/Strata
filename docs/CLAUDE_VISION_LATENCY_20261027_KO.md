# Claude 연결 경로의 비전 지연 점검 — 2026-10-27

현재 실행 중인 Unsloth UD-IQ4_XS NVFP4 fork, RTX 3090 Ti 단일, 262144 컨텍스트, CPU 비전 32스레드, 이미지 상한 1024를 사용했다. Claude Desktop 화면 조작·CUA 캡처 시간은 측정하지 않았다. Messages API의 직접 Strata 경로와 현재 Desktop 프로필에 등록된 OpenCodex 게이트웨이 경로를 확인했다.

## 확인한 결함과 수정

- 생성 ON 프로필과 ON/OFF 템플릿에는 `vision.source_cache:true`가 있었지만 구동 fork의 Vision 클래스에는 source cache 구현이 없었다. 설정만 저장되고 반복 정규화 생략은 적용되지 않는 상태였다.
- 기존 `serve/server.py`의 선택형 캐시를 재사용했다. 새 캐시 체계를 만들지 않았다. `tools/patch_nvfp4_vision_source_cache.py`는 알려진 네 구간만 적용하고, 불완전/알 수 없는 소스는 거절한다. 이미 적용된 소스는 바꾸지 않는다. 기존 Python 파일·개행·BOM·다른 fork 수정은 보존하며 기존 publish_files의 백업·동시 변경 검사를 사용한다.
- ON/OFF BAT가 다운로드된 fork의 해당 코드를 실행 전에 확인하도록 연결했다. 소스 checkout, 현재 운영 root의 두 BAT와 patcher, 실제 fork에 반영했다. 새로운 서비스나 MCP는 추가하지 않았다.
- 원본 바이트 해시 별칭만 최대 64개 보관한다. 이미지 원본/변환 바이트를 메모리에 추가 보관하지 않는다. 파일/URL은 매번 읽은 바이트로 조회하며 실패 결과와 제거된 임베딩은 재사용하지 않는다. 선택값이 없거나 false면 기존 정규화 경로를 사용한다.

## 실제 CPU 인코더 측정

1920×1080 합성 화면, PNG / lossless WebP / EXIF 회전 JPEG. 실물 strata-vision CPU 프로세스를 사용했고, 모델 생성은 하지 않았다. 각 형식 최초 처리 뒤 동일 data URI를 7회 반복한 중앙값이다. PNG 뒤 WebP는 픽셀이 같아서 기존 정규화 임베딩을 공유했다. 새 WebP 인코더 속도의 증거가 아니다.

| 반복 입력 | 수정 전 | 수정 후 | 임베딩·이미지 토큰 |
|---|---:|---:|---|
| png | 0.101ms | 0.093ms | SHA-256 동일, 1008 토큰 |
| webp | 32.161ms | 0.029ms | SHA-256 동일, 1008 토큰 |
| rotated-jpeg | 37.525ms | 0.213ms | SHA-256 동일, 1008 토큰 |

원본 bytes 입력에서도 WebP 31.935→0.007ms, 회전 JPEG 40.993→0.042ms였다. data URI 결과에는 Base64 디코딩이 포함돼 더 크다. 최초 PNG/회전 JPEG 인코딩은 약 7.5–7.8초로 유지됐다. 전체 작업 시간이 위 배율로 빨라졌다는 뜻이 아니다.

## CPU 스레드 후보

같은 이미지 3개(첫 1개 준비, 뒤 2개 측정)에서 16스레드 중앙값 10.743초, 32스레드 7.566초였다. 각 이미지 임베딩 SHA-256도 같았다. 더 느린 16스레드는 적용하지 않고 기존 32스레드를 유지했다. 모든 스레드 수를 탐색한 결과는 아니다.

## 실제 API 표본

각 경로·입력에 1회씩, 수정 전 5건과 supervisor 재시작 후 5건이다. 정답은 이미지 안의 숫자 7319이며 10/10 정확, HTTP 200, 스트림 오류 0건이다. 프롬프트/이미지 캐시가 차례로 따뜻해지고 초안 수락률·프리필 시간이 변하므로 전체 응답 시간 차이를 캐시 수정의 순수 개선율로 해석하지 않는다. 첫 이벤트는 프로토콜 이벤트이며 첫 답변 토큰과 다르다.

| 경로·표본 | 첫 프로토콜 이벤트 전→후 | 전체 요청 전→후 |
|---|---:|---:|
| direct / new-png | 7503.95→7491.80ms | 10389.59→9735.05ms |
| direct / repeat-png | 23.73→24.13ms | 410.46→170.89ms |
| direct / same-pixels-webp | 172.37→160.05ms | 308.73→285.13ms |
| direct / repeat-webp | 56.82→11.43ms | 187.21→138.78ms |
| proxy / gateway-repeat-png | 51.43→32.17ms | 168.77→138.44ms |

## 검증·시도 기록

- 소스 checkout: `python -m unittest tools.test_patch_nvfp4_vision_source_cache serve.test_vision_source_cache serve.test_vision_busy serve.test_vision_elastic tools.test_strata_iq4xs_profiles` — 28개 통과. busy/elastic의 엔진 상태는 CPU 모의 검사이다.
- 실제 fork를 import한 기존 source cache 동작 검사: source checkout의 test 파일을 runpy로 실행 — 4개 통과.
- 기존 response guard 설치 호환 검사: `python -m unittest tools.test_patch_nvfp4_response_guard` — 4개 통과. `git diff --check` 통과.
- 최초 분리 CPU 벤치마크는 운영 tools 경로가 빠져 `strata_anthropic_effort` import 단계에서 실패했다. 운영 tools 경로를 명시한 뒤 재실행했다. 첫 시도는 인코더를 시작하지 않았다.
- 실제 HTTP 준비 1건 뒤, 프록시 전체 activeTurnCount를 Strata 전용 활동으로 오인한 harness가 중단됐다. 전체 프록시 값은 다른 공급자의 Codex 작업도 포함하므로 Strata 활동과 완료 직후 cleanup만 확인하도록 고쳤다. 저장된 완료 표본은 다시 보내지 않고 남은 4건만 수행했다. API 실패나 생성 자동 재시도가 아니었다.
- fork에 test 모듈이 설치돼 있지 않아 `python -m unittest serve.test_vision_source_cache`가 import 단계에서 1회 실패했다. 운영 코드를 복사하지 않고 실제 fork를 import한 상태로 기존 source test 파일을 실행해 4개 통과했다.
- 16스레드 후보는 더 느려 제외했다. 실패/미적용 결과도 diagnostics에 보존했다.
- 기존 supervisor 재시작 영수증 `vision-source-cache-20261027-runtime-1`은 ready이다. 강제 종료나 두 번째 언어 모델 서버를 실행하지 않았다.
- 프로필 전체 SHA-256, 엔진 바이너리 SHA-256, 엔진 인자, 비전 설정이 재시작 전후 동일함을 확인했다.

## 남은 병목과 범위

새 이미지 약 7.5초는 CPU 비전 인코딩의 실측 비용이다. 현재 GPU에는 텍스트 모델·expert cache가 올라가 있으므로 근거 없이 GPU 비전으로 바꾸지 않았다. GPU 배치/VRAM 재배분, 이미지 토큰·해상도 축소는 이번 변경에 포함하지 않았다. CPU 비전 상주 약 1.1GiB를 유지해 다음 그림마다 프로세스를 다시 초기화하지 않는다. 장시간 soak, 실제 Desktop 첨부/CUA 캡처, 다중 사용자 동시 생성과 모든 이미지의 인식 정확도는 미검증이다.

원시 표본·harness·백업·재시작 영수증: `C:/Users/luiny/Strata-data/diagnostics/vision-latency-20261027/`. 커밋·푸시는 수행하지 않았다.
