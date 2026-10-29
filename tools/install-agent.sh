#!/usr/bin/env bash
set -euo pipefail
strata_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
strata_platform="$(uname -s)"
strata_plan=0
strata_role=""
strata_expect_role=0
for strata_arg in "$@"; do
  [[ "$strata_arg" != --plan ]] || strata_plan=1
  if [[ "$strata_expect_role" == 1 ]]; then strata_role="$strata_arg"; strata_expect_role=0; continue; fi
  case "$strata_arg" in --role) strata_expect_role=1 ;; --role=*) strata_role="${strata_arg#--role=}" ;; esac
done
if [[ "$strata_platform" == Darwin && "$strata_role" == server ]] || [[ "$strata_platform" == Linux && "$strata_role" == client ]]; then
  echo '이 NVFP4 서버는 Windows/Linux, 접속 PC 통합 설치는 Windows/Mac을 사용하세요.' >&2
  exit 2
fi
ensure_strata_brew() {
  for strata_brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$strata_brew" ]]; then export PATH="$(dirname -- "$strata_brew"):$PATH"; break; fi
  done
  if ! command -v brew >/dev/null 2>&1; then
    strata_bootstrap="$(mktemp -t strata-homebrew.XXXXXXXX)"
    trap 'rm -f -- "$strata_bootstrap"' EXIT
    curl --fail --location --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$strata_bootstrap"
    /bin/bash "$strata_bootstrap"
    if [[ -x /opt/homebrew/bin/brew ]]; then export PATH="/opt/homebrew/bin:$PATH"; else export PATH="/usr/local/bin:$PATH"; fi
  fi
}
if [[ "${1:-}" == --bootstrap-brew ]]; then
  [[ "$strata_platform" == Darwin ]] || { echo 'Homebrew 준비는 Mac 전용입니다.' >&2; exit 2; }
  ensure_strata_brew
  exit 0
fi
strata_python="${STRATA_CLAUDE_PYTHON:-}"
if [[ -n "$strata_python" ]]; then
  strata_python="$(command -v -- "$strata_python" || true)"
  [[ -n "$strata_python" ]] && "$strata_python" -c 'import sys; assert sys.version_info >= (3,10)' || {
    echo 'STRATA_CLAUDE_PYTHON 실행 파일을 확인하세요. 다른 경로로 대체하지 않습니다.' >&2; exit 2;
  }
else
  for strata_candidate in "$strata_root/.venv/bin/python" python3 python; do
    if command -v -- "$strata_candidate" >/dev/null 2>&1 && "$strata_candidate" -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
      strata_python="$(command -v -- "$strata_candidate")"; break
    fi
  done
fi
if [[ -z "$strata_python" ]]; then
  if [[ "$strata_plan" == 1 ]]; then echo '계획: Python 준비 후 통합 설치 계획 표시. 변경 없음.'; exit 0; fi
  if [[ "$strata_platform" == Darwin ]]; then
    ensure_strata_brew
    brew install python@3.12
    strata_python="$(brew --prefix python@3.12)/bin/python3.12"
  elif [[ "$strata_platform" == Linux ]]; then
    strata_sudo=()
    if [[ "$(id -u)" != 0 ]]; then strata_sudo=(sudo); fi
    if command -v apt-get >/dev/null 2>&1; then
      "${strata_sudo[@]}" apt-get update
      "${strata_sudo[@]}" apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
      "${strata_sudo[@]}" dnf install -y python3 python3-pip
    else echo '배포판의 Python 3.10 이상을 설치하고 다시 실행하세요.' >&2; exit 2; fi
    strata_python="$(command -v python3)"
  else echo 'Windows는 BAT 실행기를 사용하세요.' >&2; exit 2; fi
fi
"$strata_python" -c 'import sys; assert sys.version_info >= (3,10)'
exec "$strata_python" -B -X utf8 "$strata_root/tools/install_strata_agent.py" "$@"
