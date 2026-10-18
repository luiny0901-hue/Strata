#!/bin/sh
set -eu
exec sh "$(dirname "$0")/tools/remote_agent_client/setup-macos.sh" "$@"
