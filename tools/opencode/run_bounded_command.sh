#!/usr/bin/env bash
set -uo pipefail

timeout_seconds=900
heartbeat_seconds=15
log_directory="${XDG_CACHE_HOME:-$HOME/.cache}/opencode/command-logs"

usage() {
  cat >&2 <<'EOF'
Usage: run_bounded_command.sh [--timeout SECONDS] [--heartbeat SECONDS] [--log-dir DIR] -- command [args...]
Runs a non-interactive command with a wall-clock timeout and private output logs.
EOF
}

while (($#)); do
  case "$1" in
    --timeout)
      (($# >= 2)) || { usage; exit 2; }
      timeout_seconds=$2
      shift 2
      ;;
    --heartbeat)
      (($# >= 2)) || { usage; exit 2; }
      heartbeat_seconds=$2
      shift 2
      ;;
    --log-dir)
      (($# >= 2)) || { usage; exit 2; }
      log_directory=$2
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ $timeout_seconds =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: timeout must be a positive integer.' >&2; exit 2; }
[[ $heartbeat_seconds =~ ^[1-9][0-9]*$ ]] || { echo 'ERROR: heartbeat must be a positive integer.' >&2; exit 2; }
(($#)) || { usage; exit 2; }
command -v timeout >/dev/null 2>&1 || { echo 'ERROR: GNU timeout is required; no command was started.' >&2; exit 127; }

umask 077
mkdir -p -- "$log_directory" || { echo 'ERROR: could not create the command log directory.' >&2; exit 73; }
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
stdout_path="$log_directory/$run_id.stdout.log"
stderr_path="$log_directory/$run_id.stderr.log"
start_epoch=$(date +%s)
printf '[runner] started pid=%s timeout=%ss cwd=%q\n' "$$" "$timeout_seconds" "$PWD" >&2

timeout --signal=TERM --kill-after=15s "${timeout_seconds}s" "$@" </dev/null >"$stdout_path" 2>"$stderr_path" &
runner_pid=$!
next_heartbeat=$heartbeat_seconds
while kill -0 "$runner_pid" 2>/dev/null; do
  sleep 1
  elapsed=$(( $(date +%s) - start_epoch ))
  if ((elapsed >= next_heartbeat)); then
    printf '[runner] still running elapsed=%ss pid=%s\n' "$elapsed" "$runner_pid" >&2
    next_heartbeat=$((next_heartbeat + heartbeat_seconds))
  fi
done

wait "$runner_pid"
status=$?
elapsed=$(( $(date +%s) - start_epoch ))
printf '[runner] elapsed=%ss\n' "$elapsed" >&2

if [[ -s $stdout_path ]]; then
  if (( $(wc -c <"$stdout_path") > 24000 )); then
    echo '[runner] stdout preview is truncated; full output is in the log file.'
    tail -c 24000 -- "$stdout_path"
  else
    cat -- "$stdout_path"
  fi
fi
if [[ -s $stderr_path ]]; then
  if (( $(wc -c <"$stderr_path") > 24000 )); then
    echo '[runner] stderr preview is truncated; full output is in the log file.' >&2
    tail -c 24000 -- "$stderr_path" >&2
  else
    cat -- "$stderr_path" >&2
  fi
fi
printf 'LOG_STDOUT=%s\nLOG_STDERR=%s\n' "$stdout_path" "$stderr_path"

if ((status == 124 || status == 137)); then
  printf 'TIMEOUT_SECONDS=%s\nPROCESS_GROUP_TERMINATED=True\n' "$timeout_seconds" >&2
  exit 124
fi
printf 'EXIT_CODE=%s\n' "$status"
exit "$status"
