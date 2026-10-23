# 이미지 반복 전처리 개선

## 범위
같은 이미지를 대화 이력에서 다시 보낼 때, 기존 임베딩 캐시가 있어도 WebP/회전 JPEG를 정규화하는 비용이 반복됐다. vision.source_cache=true일 때 입력 바이트 SHA-256과 기존 정규화 이미지 키 사이의 별칭을 최대 64개 유지한다. 이미지 원본/변환 결과 바이트를 추가 보관하지 않는다.

파일과 URL은 매번 다시 읽고 그 바이트로 조회하므로 경로가 같아도 내용이 바뀌면 재사용하지 않는다. 임베딩 캐시에서 제거된 결과는 별칭이 있어도 재인코딩한다. 실패 결과는 저장하지 않는다. 새 이미지의 최초 인코딩 비용을 줄이는 기능은 아니다.

## CPU 측정
실제 Pillow, 1280x720 합성 이미지, 첫 처리 후 각 7회, 중앙값. 인코더 응답만 mock이므로 GPU/실제 비전 인코딩/모델 답변 시간의 증거가 아니다.

| 형식 | 기존 | 캐시 사용 |
|---|---:|---:|
| WebP | 146.224ms | 0.309ms |
| PNG | 1.367ms | 1.373ms |
| JPEG (회전 없음) | 0.324ms | 0.273ms |

원시 측정: C:/Users/luiny/Strata-data/diagnostics/vision-source-cache-20261023.json

## 검증/시도 기록
- 소스 checkout: python -m unittest serve.test_vision_source_cache serve.test_vision_busy serve.test_vision_elastic → 15개 통과. elastic 테스트의 GPU 로그는 모의 상태다.
- runtime checkout: python -m unittest serve.test_vision_source_cache → 최종 4개 통과.
- runtime은 소스 HEAD와 달라 git apply --check가 실패했다. 전체 파일을 덮어쓰지 않았다.
- 최초 runtime 적용 스크립트는 잘못된 작업 디렉터리에서 source 블록을 찾지 못해 수정 전에 중단됐다. 이어진 runtime 테스트는 모듈 미설치로 실패했다.
- 소스 checkout을 명시해 재시도하고 일치하는 3개 코드 구간만 패치했다. runtime 기존 파일은 .before-source-cache-20261023.bak으로 보관했다.

## 적용
일반 Vision 설정의 기본값은 꺼짐이다. 사용자가 요청한 ON/OFF launcher 전용 profile template에는 source_cache=true를 명시했다. 런처가 다음 서버 실행에서 profile을 다시 렌더링할 때 적용된다. 실행 중 서버는 재시작하지 않았다.

이미지 해상도/토큰 수/추론 강도를 낮추지 않았다. 실제 Rider 첨부→비전 인코딩→최종 답변, 최초 큰 이미지, 다중 이미지, 네트워크 업로드 시간은 이번에 실측하지 않았다. 실제 서버에 전체 병목이 없다고 주장하지 않는다.
