#!/usr/bin/env bash
set -euo pipefail

strata_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
strata_python="${STRATA_CLAUDE_PYTHON:-$strata_root/.venv/bin/python}"
if [[ ! -x "$strata_python" ]]; then
  if [[ -n "${STRATA_CLAUDE_PYTHON:-}" ]]; then
    strata_selected="$(command -v -- "$strata_python" || true)"
    if [[ -n "$strata_selected" && -x "$strata_selected" ]]; then
      export STRATA_CLAUDE_PYTHON="$strata_selected"
      exec bash "$strata_root/setup-claude-opencodex.sh" "$@"
    fi
    echo "STRATA_CLAUDE_PYTHON 실행 파일을 확인하세요: $strata_python" >&2
    exit 127
  fi
  if command -v python3 >/dev/null 2>&1; then
    strata_python="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    strata_python="$(command -v python)"
  else
    echo 'Python 3를 찾지 못했습니다. Python 3을 설치한 뒤 다시 실행하세요.' >&2
    exit 127
  fi
fi

action=setup
if [[ "${1:-}" == "clients" ]]; then
  shift
  exec "$strata_python" "$strata_root/tools/strata_client_settings.py" --codex "$@"
fi
if [[ "${1:-}" == "doctor" ]]; then
  action=doctor
  shift
fi
exec "$strata_python" "$strata_root/tools/claude_opencodex_client.py" "$action" "$@"
