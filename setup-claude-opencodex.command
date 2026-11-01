#!/bin/bash
strata_root="$(cd -- "$(dirname -- "$0")" && pwd)"
bash "$strata_root/setup-claude-opencodex.sh" "$@"
strata_result=$?
if [ "$strata_result" -ne 0 ]; then
  echo '설치·외부 PC 안내: https://claude.com/download'
  echo "연결 안내: $strata_root/docs/CLAUDE_OPENCODEX_KO.md"
fi
if [ "$#" -eq 0 ]; then read -r -p 'Enter를 누르면 닫힙니다. ' _strata_reply; fi
exit "$strata_result"
