#!/usr/bin/env bash
set -euo pipefail
strata_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$strata_root/tools/install-agent.sh" "$@"
