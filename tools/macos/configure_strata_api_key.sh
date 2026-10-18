#!/usr/bin/env bash
set -euo pipefail

target="$HOME/.config/strata/STRATA_API_KEY"
directory="$(dirname "$target")"
mkdir -p "$directory"
chmod 700 "$directory"

read -r -s -p 'Paste the Strata API key (input hidden): ' key
printf '\n'
if [[ ! "$key" =~ ^[[:xdigit:]]{64}$ ]]; then
  unset key
  printf 'ERROR: the key must be exactly 64 hexadecimal characters. No file was written.\n' >&2
  exit 2
fi

temporary="$(mktemp "$directory/STRATA_API_KEY.XXXXXX")"
trap 'rm -f "$temporary"; unset key' EXIT
chmod 600 "$temporary"
printf '%s' "$key" >"$temporary"
mv -f "$temporary" "$target"
trap - EXIT
unset key
printf 'Saved the key to %s with mode 600. The key value was not displayed.\n' "$target"
