#!/bin/sh
set -eu

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3 is required. Install Python 3 for this user, then rerun this script.' >&2
  exit 2
fi

exec python3 "$(dirname "$0")/setup_client.py" "$@"
