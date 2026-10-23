#!/bin/bash
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
while true; do
  printf '\n%s\n' 'Strata 코딩 도우미' \
    '1. 처음 설정 / 연결 주소 변경 (필요한 프로그램도 설치)' \
    '2. 사용 시작' '3. 연결 문제 확인' '5. 현재 작업 설정 내보내기' '0. 종료' \
    '다른 PC의 서버를 사용한다면 1번부터 시작하세요.'
  read -r -p '번호를 입력하고 Enter: ' choice || exit 0
  case "$choice" in
    1) action=setup ;;
    2) action=run ;;
    3) action=doctor ;;
    5) action=export-profile ;;
    0) exit 0 ;;
    *) continue ;;
  esac
  if sh "$ROOT/setup-opencode.sh" "$action"; then
    if [ "$action" = setup ]; then
      printf '%s\n' '설정을 마쳤습니다. 2번으로 시작하거나 Rider를 다시 열고 OpenCode Strata를 선택하세요.'
    fi
  else
    printf '%s\n' '완료되지 않았습니다. 위 오류를 확인하세요. 같은 메뉴를 다시 선택할 수 있습니다.'
  fi
  read -r -p 'Enter를 누르면 메뉴로 돌아갑니다: ' ignored || exit 0
done
