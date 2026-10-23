#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
[ "$(uname -s)" = Linux ] || { echo 'Linux is required.' >&2; exit 2; }
echo 'Preparing Python/server dependencies. No GPU driver, engine or model is downloaded; no server is started.'
if ! python3 -c 'import sys,venv,ensurepip;sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  if [ "$(id -u)" -eq 0 ]; then SUDO=; else SUDO=sudo; fi
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y python3 python3-pip
  else
    echo 'Install Python 3.10+ with venv and pip using your distribution package manager, then rerun.' >&2; exit 2
  fi
fi
python3 -c 'import sys,venv,ensurepip;sys.exit(0 if sys.version_info >= (3,10) else 1)' || { echo 'Python 3.10+ with venv is required.' >&2; exit 2; }
TARGET_PYTHON="$ROOT/.venv/bin/python"
expect_python=0
for option in "$@"; do
  if [ "$expect_python" = 1 ]; then TARGET_PYTHON=$option; expect_python=0; continue; fi
  case "$option" in
    --python) expect_python=1 ;;
    --python=*) TARGET_PYTHON=${option#--python=} ;;
  esac
done
[ "$expect_python" = 0 ] && [ -n "$TARGET_PYTHON" ] || { echo '--python needs an executable path.' >&2; exit 2; }
case "$TARGET_PYTHON" in '~/'*) TARGET_PYTHON="$HOME/${TARGET_PYTHON#\~/}" ;; esac
if [ "$TARGET_PYTHON" != "$ROOT/.venv/bin/python" ] && [ ! -x "$TARGET_PYTHON" ]; then
  echo 'The selected Python environment does not exist or is not executable. Existing paths were preserved.' >&2; exit 2
fi
if [ "$TARGET_PYTHON" = "$ROOT/.venv/bin/python" ] && [ ! -x "$TARGET_PYTHON" ]; then
  if [ -e "$ROOT/.venv" ]; then echo 'Existing .venv is incomplete or from another OS. Select a new checkout; existing files were preserved.' >&2; exit 2; fi
  python3 -m venv "$ROOT/.venv"
fi
"$TARGET_PYTHON" -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) and sys.prefix != sys.base_prefix else 1)' || { echo 'Use a Python 3.10+ virtual environment; system Python is not modified.' >&2; exit 2; }
"$TARGET_PYTHON" -m pip install -r "$ROOT/requirements.txt"
"$TARGET_PYTHON" "$ROOT/tools/linux_nvfp4_server.py" prepare "$@"
echo 'Python dependencies and profiles are prepared. Follow docs/LINUX_NVFP4_SERVER_KO.md for the matching fork artifacts and any additional fork dependencies.'
