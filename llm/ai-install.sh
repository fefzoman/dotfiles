#!/usr/bin/env bash

export RTK_TELEMETRY_DISABLED=1
export HEADROOM_BEACON=off
export CTX7_TELEMETRY_DISABLED=1
export MCP_TIMEOUT="${MCP_TIMEOUT:-60000}"

__codex_answer() {
  local dir out err rc

  dir="$(mktemp -d "${TMPDIR:-/tmp}/codex-answer.XXXXXX")" || return 1
  out="$dir/answer"
  err="$dir/error"

  if (( $# > 0 )); then
    codex --ask-for-approval never exec \
      --model gpt-5.6-luna \
      -c model_reasoning_effort=\"medium\" \
      --sandbox read-only \
      --skip-git-repo-check \
      --output-last-message "$out" \
      "$*" \
      >/dev/null 2>"$err" && rc=0 || rc=$?
  else
    codex --ask-for-approval never exec \
      --model gpt-5.6-luna \
      -c model_reasoning_effort=\"medium\" \
      --sandbox read-only \
      --skip-git-repo-check \
      --output-last-message "$out" \
      - \
      >/dev/null 2>"$err" && rc=0 || rc=$?
  fi

  [[ ! -s "$out" ]] || cat "$out"
  if (( rc != 0 )) && [[ -s "$err" ]]; then
    cat "$err" >&2
  fi
  rm -f "$out" "$err"
  rmdir "$dir"
  return "$rc"
}

alias '??'='__codex_answer'

codex() {
  local codex_home="${CODEX_HOME:-$HOME/.codex}"

  if command -v headroom >/dev/null 2>&1; then
    CODEX_HOME="$codex_home" command headroom wrap codex \
      --code-memory none -- "$@"
  else
    CODEX_HOME="$codex_home" command codex "$@"
  fi
}

claude() {
  local claude_config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

  if command -v headroom >/dev/null 2>&1; then
    CLAUDE_CONFIG_DIR="$claude_config_dir" command headroom wrap claude \
      --code-memory none -- "$@"
  else
    CLAUDE_CONFIG_DIR="$claude_config_dir" command claude "$@"
  fi
}

code() {
  CODEX_HOME="${CODEX_HOME:-$HOME/.codex}" command code "$@"
}

alias claude-work='CLAUDE_CONFIG_DIR="$HOME/.claude-work" claude'
alias codex-work='CODEX_HOME="$HOME/.codex-work" codex'

code-work() {
  CODEX_HOME="$HOME/.codex-work" \
    CLAUDE_CONFIG_DIR="$HOME/.claude-work" \
    code --user-data-dir "$HOME/.vscode-work" "$@"
}

claude-code-work() {
  CLAUDE_CONFIG_DIR="$HOME/.claude-work" \
    code --user-data-dir "$HOME/.vscode-claude-work" "$@"
}

# Sourcing configures the shell; executing continues with installation.
[[ "${BASH_SOURCE[0]}" != "$0" ]] && return 0

set -euo pipefail

export HOMEBREW_NO_REQUIRE_TAP_TRUST=1
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"
PYTHON_VERSION=3.13

install_ai_tools() {
  if [[ "$OS" == Darwin ]]; then
    command -v brew >/dev/null 2>&1 || { echo "Homebrew is required." >&2; exit 1; }
    brew list --cask codex >/dev/null 2>&1 || brew install --cask codex
    brew list --formula node >/dev/null 2>&1 || brew install node
    brew list --formula rtk >/dev/null 2>&1 || brew install rtk
    type -P uv >/dev/null 2>&1 || brew install uv
  elif [[ "$OS" == Linux ]]; then
    command -v npm >/dev/null 2>&1 || { echo "npm is required." >&2; exit 1; }
    npm install --global --prefix "$HOME/.local" @openai/codex
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh |
      env RTK_INSTALL_DIR="$HOME/.local/bin" sh
  else
    echo "Unsupported operating system: $OS" >&2
    exit 1
  fi

  npm install --global --prefix "$HOME/.local" \
    @anthropic-ai/claude-code@latest @upstash/context7-mcp@latest
  UV_TOOL_BIN_DIR="$HOME/.local/bin" "$(type -P uv)" tool install \
    --python "$PYTHON_VERSION" --upgrade serena-agent
}

configure_rtk() {
  local profile rtk_bin shell_path

  rtk_bin="$(command -v rtk)"
  shell_path="$(dirname "$rtk_bin"):$PATH"
  RTK_TELEMETRY_DISABLED=1 "$rtk_bin" telemetry disable
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    RTK_TELEMETRY_DISABLED=1 CODEX_HOME="$profile" \
      "$rtk_bin" init -g --codex --no-trust-filters
    python - "$profile/config.toml" "$shell_path" <<'PY'
import json
import re
import sys
from pathlib import Path

config = Path(sys.argv[1])
path = sys.argv[2]
text = config.read_text(encoding="utf-8") if config.exists() else ""
begin = "# BEGIN AI TOOLING SHELL ENVIRONMENT"
end = "# END AI TOOLING SHELL ENVIRONMENT"
text = re.sub(
    rf"\n?{re.escape(begin)}.*?{re.escape(end)}\n?",
    "\n",
    text,
    flags=re.DOTALL,
)
if re.search(r"(?m)^\s*(?:\[shell_environment_policy(?:\.|\])|shell_environment_policy\.)", text):
    raise SystemExit(
        f"{config} already defines shell_environment_policy; add {path!r} to its PATH"
    )
block = (
    f"{begin}\n"
    "[shell_environment_policy]\n"
    f"set = {{ PATH = {json.dumps(path)} }}\n"
    f"{end}\n"
)
config.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
PY
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    RTK_TELEMETRY_DISABLED=1 CLAUDE_CONFIG_DIR="$profile" \
      "$rtk_bin" init -g --agent claude --auto-patch --no-trust-filters
  done
}

install_ponytail() {
  local claude_bin codex_bin profile

  codex_bin="$(type -P codex)"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace add \
      DietrichGebert/ponytail --json >/dev/null
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace upgrade \
      ponytail --json >/dev/null
    CODEX_HOME="$profile" "$codex_bin" plugin add \
      ponytail@ponytail --json >/dev/null
    echo "==> Ponytail installed for $profile"
  done

  claude_bin="$(type -P claude)"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    CLAUDE_CONFIG_DIR="$profile" "$claude_bin" plugin marketplace add \
      DietrichGebert/ponytail >/dev/null 2>&1 ||
      CLAUDE_CONFIG_DIR="$profile" "$claude_bin" plugin marketplace update \
        ponytail >/dev/null
    CLAUDE_CONFIG_DIR="$profile" "$claude_bin" plugin install \
      --scope user --yes ponytail@ponytail --json >/dev/null 2>&1 ||
      CLAUDE_CONFIG_DIR="$profile" "$claude_bin" plugin update \
        --scope user --yes ponytail@ponytail --json >/dev/null
    echo "==> Ponytail installed for $profile"
  done
}

configure_agent_mcps() {
  local claude_bin codex_bin context7_bin profile serena_bin server

  claude_bin="$(type -P claude)"
  codex_bin="$(type -P codex)"
  context7_bin="$(type -P context7-mcp)"
  serena_bin="$(type -P serena)"

  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    for server in serena context7; do
      CODEX_HOME="$profile" "$codex_bin" mcp remove "$server" >/dev/null 2>&1 || true
    done
    CODEX_HOME="$profile" "$codex_bin" mcp add serena -- \
      "$serena_bin" start-mcp-server --context=codex --project-from-cwd \
      --open-web-dashboard false \
    CODEX_HOME="$profile" "$codex_bin" mcp add context7 -- \
      "$context7_bin" --transport stdio
  done

  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    for server in serena context7; do
      CLAUDE_CONFIG_DIR="$profile" "$claude_bin" mcp remove \
        --scope user "$server" >/dev/null 2>&1 || true
    done
    CLAUDE_CONFIG_DIR="$profile" "$claude_bin" mcp add --scope user serena -- \
      "$serena_bin" start-mcp-server --context=claude-code --project-from-cwd \
      --open-web-dashboard false \
    CLAUDE_CONFIG_DIR="$profile" "$claude_bin" mcp add --scope user context7 -- \
      "$context7_bin" --transport stdio
  done
}

install_headroom() {
  UV_TOOL_BIN_DIR="$HOME/.local/bin" "$(command -v uv)" tool install \
    --python "$PYTHON_VERSION" --upgrade 'headroom-ai[proxy,code]'
}

install_global_agents() {
  local profile

  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/AGENTS.md" "$profile/AGENTS.md"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/AGENTS.md" "$profile/CLAUDE.md"
  done
}

install_codex_compact_warning() {
  local config_dir="$HOME/.config/dotfiles" hooks profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/codex_compact_warning.py" \
    "$config_dir/codex_compact_warning.py"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    hooks="$profile/hooks.json"
    if [[ ! -e "$hooks" ]] || cmp -s "$SCRIPT_DIR/codex-hooks.json" "$hooks"; then
      install -m 0644 "$SCRIPT_DIR/codex-hooks.json" "$hooks"
    else
      echo "Warning: preserving existing $hooks; merge codex-hooks.json manually." >&2
    fi
  done
}

install_claude_compact_statusline() {
  local config_dir="$HOME/.config/dotfiles" profile settings

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/claude_compact_statusline.py" \
    "$config_dir/claude_compact_statusline.py"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    settings="$profile/settings.json"
    python - "$settings" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
owned = {
    "type": "command",
    "command": 'python3 "$HOME/.config/dotfiles/claude_compact_statusline.py"',
}
current = data.get("statusLine")
if current not in (None, owned):
    print(f"Warning: preserving existing {path} statusLine.", file=sys.stderr)
else:
    data["statusLine"] = owned
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
  done
}

install_shell_config() {
  local config_dir="$HOME/.config/dotfiles"

  mkdir -p "$config_dir"
  install -m 0644 "$SCRIPT_DIR/ai-install.sh" "$config_dir/ai-install.sh"
  if ! grep -q '^# BEGIN AI TOOLING$' "$HOME/.bashrc" 2>/dev/null; then
    cat >> "$HOME/.bashrc" <<'EOF'

# BEGIN AI TOOLING
source "$HOME/.config/dotfiles/ai-install.sh"
# END AI TOOLING
EOF
  fi
}

echo "==> Installing AI command-line tools..."
install_ai_tools
echo "==> Installing global Codex and Claude instructions..."
install_global_agents
echo "==> Installing Codex compact-warning hook..."
install_codex_compact_warning
echo "==> Configuring RTK for Codex and Claude profiles..."
configure_rtk
echo "==> Installing Claude compact-warning status line..."
install_claude_compact_statusline
echo "==> Installing Ponytail for Codex and Claude profiles..."
install_ponytail
echo "==> Configuring Serena and Context7 for Codex and Claude profiles..."
configure_agent_mcps
echo "==> Installing Headroom for Codex and Claude..."
install_headroom
echo "==> Installing Codex and Claude token profiler..."
bash "$SCRIPT_DIR/token-profiler/install.sh"
echo "==> Installing AI shell configuration..."
install_shell_config
echo "==> Review and trust Ponytail hooks with /hooks in each Codex profile."
echo "==> Running LLM toolchain smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"
