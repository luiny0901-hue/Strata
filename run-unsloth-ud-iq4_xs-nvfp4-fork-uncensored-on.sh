#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$ROOT/tools/linux_nvfp4_server.py" run --mode on "$@"
