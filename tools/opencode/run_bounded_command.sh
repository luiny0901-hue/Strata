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
case "${1##*/}" in
  sudo|gsudo|runas|runas.exe)
    echo 'BLOCKED_UAC: privilege elevation requires an authorized existing context; no command started.' >&2
    exit 77
    ;;
esac
export CI=true NO_COLOR=1 GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never
export SUDO_ASKPASS= SSH_ASKPASS=
timeout_command="$(command -v timeout || command -v gtimeout || true)"
[[ -n $timeout_command ]] || { echo 'ERROR: GNU timeout or gtimeout is required; no command was started.' >&2; exit 127; }

umask 077
mkdir -p "$log_directory" || { echo 'ERROR: could not create the command log directory.' >&2; exit 73; }
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
stdout_path="$log_directory/$run_id.stdout.log"
stderr_path="$log_directory/$run_id.stderr.log"
start_epoch=$(date +%s)
printf '[runner] started pid=%s timeout=%ss cwd=%q\n' "$$" "$timeout_seconds" "$PWD" >&2

"$timeout_command" --signal=TERM --kill-after=15s "${timeout_seconds}s" "$@" </dev/null >"$stdout_path" 2>"$stderr_path" &
runner_pid=$!
cancel_runner() {
  local status=$1
  trap '' INT TERM HUP
  # GNU timeout owns this process group (we do not use --foreground).
  kill -TERM -- "-$runner_pid" 2>/dev/null || kill -TERM "$runner_pid" 2>/dev/null || true
  for ((n=0; n<30; n++)); do
    kill -0 -- "-$runner_pid" 2>/dev/null || break
    sleep 0.1
  done
  kill -KILL -- "-$runner_pid" 2>/dev/null || true
  wait "$runner_pid" 2>/dev/null || true
  printf 'CANCELLED=True\nLOG_STDOUT=%s\nLOG_STDERR=%s\n' "$stdout_path" "$stderr_path" >&2
  exit "$status"
}
trap 'cancel_runner 130' INT
trap 'cancel_runner 143' TERM HUP
# Progress reporting must not delay command completion by a polling interval.
# The monitor owns its sleep child and stops it when the runner exits/cancels.
(
  trap - EXIT INT TERM HUP
  heartbeat_sleep=
  stop_monitor() {
    if [[ -n $heartbeat_sleep ]]; then
      kill "$heartbeat_sleep" 2>/dev/null || true
      wait "$heartbeat_sleep" 2>/dev/null || true
    fi
    exit 0
  }
  trap stop_monitor TERM HUP INT
  while kill -0 "$runner_pid" 2>/dev/null; do
    sleep "$heartbeat_seconds" &
    heartbeat_sleep=$!
    wait "$heartbeat_sleep" || break
    heartbeat_sleep=
    kill -0 "$runner_pid" 2>/dev/null || break
    elapsed=$(( $(date +%s) - start_epoch ))
    printf '[runner] still running elapsed=%ss pid=%s\n' "$elapsed" "$runner_pid" >&2
  done
) &
heartbeat_pid=$!
cleanup_monitor() {
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
}
trap cleanup_monitor EXIT

wait "$runner_pid"
status=$?
cleanup_monitor
trap - EXIT
elapsed=$(( $(date +%s) - start_epoch ))
printf '[runner] elapsed=%ss\n' "$elapsed" >&2

if [[ -s $stdout_path ]]; then
  if (( $(wc -c <"$stdout_path") > 24000 )); then
    echo '[runner] stdout preview is truncated; full output is in the log file.'
    tail -c 24000 "$stdout_path"
  else
    cat "$stdout_path"
  fi
fi
if [[ -s $stderr_path ]]; then
  if (( $(wc -c <"$stderr_path") > 24000 )); then
    echo '[runner] stderr preview is truncated; full output is in the log file.' >&2
    tail -c 24000 "$stderr_path" >&2
  else
    cat "$stderr_path" >&2
  fi
fi
printf 'LOG_STDOUT=%s\nLOG_STDERR=%s\n' "$stdout_path" "$stderr_path"

if ((status == 124)); then
  printf 'TIMEOUT_SECONDS=%s\nPROCESS_GROUP_TERMINATED=True\n' "$timeout_seconds" >&2
  exit 124
fi
printf 'EXIT_CODE=%s\n' "$status"
exit "$status"
