#!/bin/sh
set -eu
if [ "$#" -eq 0 ]; then set -- setup; fi

if [ "$1" = setup ]; then
  if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo 'This client bootstrap requires Apple Silicon macOS.' >&2; exit 2
  fi
  export PATH="$HOME/.local/bin:/opt/homebrew/opt/node@24/bin:/opt/homebrew/opt/python@3.12/libexec/bin:/opt/homebrew/bin:$PATH"
  echo 'Setup installs missing Homebrew, Python, Node, coreutils and OpenCode V2; CUA/REA setup follows.'
  echo 'Homebrew may request your macOS password. System permissions must be approved by you.'
  if ! command -v brew >/dev/null 2>&1; then
    installer=$(mktemp -t strata-homebrew)
    trap 'rm -f "$installer"' EXIT HUP INT TERM
    curl --fail --show-error --location --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
    /bin/bash "$installer"
    rm -f "$installer"
    trap - EXIT HUP INT TERM
  fi
  BREW=$(command -v brew) || { echo 'Homebrew installation did not complete. Rerun first setup.' >&2; exit 2; }
  brew_environment=$("$BREW" shellenv)
  eval "$brew_environment"
  export HOMEBREW_NO_INSTALL_CLEANUP=1
  if ! python3 -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then brew install python@3.12; export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"; fi
  if command -v node >/dev/null 2>&1; then
    node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit((a===22&&b>=19)||(a===24&&b>=11)||a>=26?0:1)' || { echo 'Existing Node is too old for REA. Upgrade Node, then rerun; existing runtime was preserved.' >&2; exit 2; }
  else
    brew install node@24
    export PATH="$(brew --prefix node@24)/bin:$PATH"
  fi
  # A keg-only Node/Python must remain discoverable on later run/doctor calls.
  if ! command -v gtimeout >/dev/null 2>&1; then brew install coreutils; fi
  if ! command -v opencode >/dev/null 2>&1; then npm install --global --prefix "$HOME/.local" @opencode/cli@2.0.22; fi
fi
export PATH="$HOME/.local/bin:/opt/homebrew/opt/node@24/bin:/opt/homebrew/opt/python@3.12/libexec/bin:/opt/homebrew/bin:$PATH"

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3 is required. Install Python 3 for this user, then rerun this script.' >&2
  exit 2
fi

exec python3 "$(dirname "$0")/setup_client.py" "$@"
