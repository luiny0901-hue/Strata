#!/bin/bash
strata_root="$(cd -- "$(dirname -- "$0")" && pwd)"
bash "$strata_root/install-strata-agent.sh" "$@"
strata_result=$?
if [ "$#" -eq 0 ]; then read -r -p 'Enter를 누르면 닫힙니다. ' _strata_reply; fi
exit "$strata_result"
