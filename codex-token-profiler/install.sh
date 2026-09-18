#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"
TARGET="${TARGET_DIR}/codex-usage"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 is required to install codex-token-profiler." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "pip is required for $PYTHON_BIN." >&2
  exit 1
fi

echo "Installing required Python package: tiktoken"
env PIP_BREAK_SYSTEM_PACKAGES=1 "$PYTHON_BIN" -m pip install --upgrade tiktoken
"$PYTHON_BIN" -c 'import tiktoken'

mkdir -p "${TARGET_DIR}"
cp "${HERE}/codex-usage" "${TARGET}"
chmod +x "${TARGET}"

echo "Installed: ${TARGET}"

case ":${PATH}:" in
  *":${TARGET_DIR}:"*) ;;
  *)
    echo
    echo "NOTE: ${TARGET_DIR} is not currently on PATH."
    echo 'For zsh:'
    echo '  echo '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> ~/.zshrc'
    echo '  source ~/.zshrc'
    ;;
esac

echo
echo "Try:"
echo "  codex-usage current"
