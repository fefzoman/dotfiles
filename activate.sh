#!/usr/bin/env bash
set -euo pipefail

export HOMEBREW_NO_REQUIRE_TAP_TRUST=1

usage() { echo "Usage: $0 [auto-approve]" >&2; exit 2; }
(( $# <= 1 )) || usage
[[ $# == 0 || $1 == auto-approve ]] || usage

if [[ ${1:-} == auto-approve ]]; then
  export DOTFILES_AUTO_APPROVE=1 NONINTERACTIVE=1 DEBIAN_FRONTEND=noninteractive
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASIC_INSTALL="${SCRIPT_DIR}/basic-install.sh"
RESET_SCRIPT="${SCRIPT_DIR}/reset-to-bash-ohmybash.sh"

echo "==> Running basic install..."
bash "$BASIC_INSTALL"

if ! command -v brew >/dev/null 2>&1; then
  for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$brew_bin" ]] || continue
    eval "$("$brew_bin" shellenv)"
    break
  done
fi

echo "==> Resetting to Bash + Oh My Bash..."
BASH_BIN="$(command -v bash || true)"
if command -v brew >/dev/null 2>&1; then
  BREW_BASH_PREFIX="$(brew --prefix bash 2>/dev/null || true)"
  [[ -n "$BREW_BASH_PREFIX" && -x "${BREW_BASH_PREFIX}/bin/bash" ]] && BASH_BIN="${BREW_BASH_PREFIX}/bin/bash"
fi

[[ -x "$BASH_BIN" ]] || { echo "bash not found in PATH." >&2; exit 1; }

"$BASH_BIN" "$RESET_SCRIPT"

echo "==> Combined setup complete."
echo "==> Restart Alacritty to load the new shell configuration."
