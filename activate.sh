#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASIC_INSTALL="${SCRIPT_DIR}/basic-install.sh"
RESET_SCRIPT="${SCRIPT_DIR}/reset-to-bash-ohmybash.sh"

if [[ ! -f "$BASIC_INSTALL" ]]; then
  echo "Missing script: $BASIC_INSTALL" >&2
  exit 1
fi

if [[ ! -f "$RESET_SCRIPT" ]]; then
  echo "Missing script: $RESET_SCRIPT" >&2
  exit 1
fi

echo "==> Running basic install..."
bash "$BASIC_INSTALL"

# If Homebrew was installed during the first step, make it available to this
# shell before starting the reset step.
if ! command -v brew >/dev/null 2>&1; then
  for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$brew_bin" ]]; then
      eval "$("$brew_bin" shellenv)"
      break
    fi
  done
fi

echo "==> Resetting to Bash + Oh My Bash..."
bash "$RESET_SCRIPT"

echo "==> Combined setup complete."

if [[ -f "${HOME}/.bashrc" ]]; then
  source "${HOME}/.bashrc"
fi
