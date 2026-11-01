#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" = "--managed" ]; then
    shift
    exec python3 "$ROOT/tools/strata_server_supervisor.py" --launcher "$ROOT/run-unsloth-ud-iq4_xs-nvfp4-fork-uncensored-on.sh" --state-dir "$HOME/Strata-data/supervisor" --api-key-file "${XDG_CONFIG_HOME:-$HOME/.config}/strata/STRATA_API_KEY" --token-file "${XDG_CONFIG_HOME:-$HOME/.config}/strata/server-control/restart-control.key" "$@"
fi
exec python3 "$ROOT/tools/linux_nvfp4_server.py" run --mode on "$@"
