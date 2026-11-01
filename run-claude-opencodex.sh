#!/usr/bin/env bash
set -euo pipefail
strata_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
strata_python="${STRATA_CLAUDE_PYTHON:-$strata_root/.venv/bin/python}"
if [[ ! -x "$strata_python" ]]; then
  if [[ -n "${STRATA_CLAUDE_PYTHON:-}" ]]; then
    strata_selected="$(command -v -- "$strata_python" || true)"
    if [[ -n "$strata_selected" && -x "$strata_selected" ]]; then
      exec "$strata_selected" "$strata_root/tools/claude_opencodex_client.py" run "$@"
    fi
    echo "STRATA_CLAUDE_PYTHON 실행 파일을 확인하세요: $strata_python" >&2
    exit 127
  fi
  if command -v python3 >/dev/null 2>&1; then
    strata_python="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    strata_python="$(command -v python)"
  else
    echo 'Python 3 not found. Install Python 3 and try again.' >&2
    exit 127
  fi
fi
exec "$strata_python" "$strata_root/tools/claude_opencodex_client.py" run "$@"
