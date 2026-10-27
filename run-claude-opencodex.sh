#!/usr/bin/env bash
set -euo pipefail
strata_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
strata_python="${STRATA_CLAUDE_PYTHON:-$strata_root/.venv/bin/python}"
if [[ ! -x "$strata_python" ]]; then
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
