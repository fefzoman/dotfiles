#!/usr/bin/env bash

export RTK_TELEMETRY_DISABLED=1
export HEADROOM_BEACON=off
export TRANSFORMERS_VERBOSITY=error
export CTX7_TELEMETRY_DISABLED=1
export MCP_TIMEOUT="${MCP_TIMEOUT:-60000}"

__codex_answer() {
  local dir out err rc

  dir="$(mktemp -d "${TMPDIR:-/tmp}/codex-answer.XXXXXX")" || return 1
  out="$dir/answer"
  err="$dir/error"

  codex --ask-for-approval never exec \
    --model gpt-6-sol \
    -c model_reasoning_effort=\"medium\" \
    --sandbox read-only \
    --skip-git-repo-check \
    --output-last-message "$out" \
    "${*:--}" \
    >/dev/null 2>"$err" && rc=0 || rc=$?

  [[ ! -s "$out" ]] || cat "$out"
  if (( rc != 0 )) && [[ -s "$err" ]]; then
    cat "$err" >&2
  fi
  rm -f "$out" "$err"
  rmdir "$dir"
  return "$rc"
}

alias '??'='__codex_answer'

# Headroom routing lives in each profile's config (see install_headroom), so
# codex, claude and the VS Code extensions all reach the persistent proxy.
code() {
  env -u CLAUDE_CONFIG_DIR CODEX_HOME="$HOME/.codex" code "$@"
}

alias claude-work='CLAUDE_CONFIG_DIR="$HOME/.claude-work" claude'
alias codex-work='CODEX_HOME="$HOME/.codex-work" codex'

# Sourcing configures the shell; executing continues with installation.
[[ "${BASH_SOURCE[0]}" != "$0" ]] && return 0

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"
PYTHON_VERSION=3.13

agent_config() {
  python "$SCRIPT_DIR/agent_config.py" "$@"
}

# The default Claude profile must run without CLAUDE_CONFIG_DIR: setting it,
# even to ~/.claude, moves user MCPs to ~/.claude/.claude.json, which the
# VS Code extension never reads.
with_claude_profile() {
  local profile="$1"
  shift
  if [[ "$profile" == "$HOME/.claude" ]]; then
    env -u CLAUDE_CONFIG_DIR "$@"
  else
    CLAUDE_CONFIG_DIR="$profile" "$@"
  fi
}

install_ai_tools() {
  if [[ "$OS" == Darwin ]]; then
    command -v brew >/dev/null 2>&1 || { echo "Homebrew is required." >&2; exit 1; }
    brew update || return
    if brew list --cask codex >/dev/null 2>&1; then
      brew upgrade --cask codex || return
    else
      brew install --cask codex || return
    fi
    brew list --formula node >/dev/null 2>&1 || brew install node
    brew list --formula rtk >/dev/null 2>&1 || brew install rtk
    type -P uv >/dev/null 2>&1 || brew install uv
  elif [[ "$OS" == Linux ]]; then
    command -v npm >/dev/null 2>&1 || { echo "npm is required." >&2; exit 1; }
    npm install --global --prefix "$HOME/.local" @openai/codex@latest
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh |
      env RTK_INSTALL_DIR="$HOME/.local/bin" sh
  else
    echo "Unsupported operating system: $OS" >&2
    exit 1
  fi

  npm install --global --prefix "$HOME/.local" @upstash/context7-mcp@latest
  curl -fsSL https://claude.ai/install.sh | bash -s latest
  curl -fsSL https://raw.githubusercontent.com/danielmiessler/Fabric/main/scripts/installer/install.sh |
    env INSTALL_DIR="$HOME/.local/bin" bash
  UV_TOOL_BIN_DIR="$HOME/.local/bin" "$(type -P uv)" tool install \
    --python "$PYTHON_VERSION" --upgrade serena-agent
}

install_vscode_commands() {
  local vscode_cli="/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"

  mkdir -p "$HOME/.local/bin"
  if ! type -P code >/dev/null 2>&1; then
    if [[ "$OS" != Darwin || ! -x "$vscode_cli" ]]; then
      echo "VS Code's code command is required." >&2
      return 1
    fi
    ln -s "$vscode_cli" "$HOME/.local/bin/code"
  fi

  install -m 0755 "$SCRIPT_DIR/code-work" "$HOME/.local/bin/code-work"
}

configure_rtk() {
  local profile rtk_bin shell_path

  rtk_bin="$(command -v rtk)"
  shell_path="$(dirname "$rtk_bin"):$PATH"
  RTK_TELEMETRY_DISABLED=1 "$rtk_bin" telemetry disable
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    RTK_TELEMETRY_DISABLED=1 CODEX_HOME="$profile" \
      "$rtk_bin" init -g --codex --no-trust-filters
    agent_config codex-shell-path "$profile/config.toml" "$shell_path"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    RTK_TELEMETRY_DISABLED=1 with_claude_profile "$profile" \
      "$rtk_bin" init -g --agent claude --auto-patch --no-trust-filters
  done
}

install_ponytail() {
  local claude_bin codex_bin profile

  codex_bin="$(type -P codex)"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace add \
      DietrichGebert/ponytail --json >/dev/null 2>&1 || {
      # A 'ponytail' marketplace left over from another source blocks the add.
      CODEX_HOME="$profile" "$codex_bin" plugin marketplace remove \
        ponytail >/dev/null 2>&1 || true
      CODEX_HOME="$profile" "$codex_bin" plugin marketplace add \
        DietrichGebert/ponytail --json >/dev/null
    }
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace upgrade \
      ponytail --json >/dev/null
    CODEX_HOME="$profile" "$codex_bin" plugin add \
      ponytail@ponytail --json >/dev/null
    sed -i.bak 's/^codex_hooks[[:space:]]*=/hooks =/' "$profile/config.toml"
    rm -f "$profile/config.toml.bak"
    echo "==> Ponytail installed for $profile"
  done

  claude_bin="$(type -P claude)"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    with_claude_profile "$profile" "$claude_bin" plugin marketplace add \
      DietrichGebert/ponytail >/dev/null 2>&1 ||
      with_claude_profile "$profile" "$claude_bin" plugin marketplace update \
        ponytail >/dev/null
    with_claude_profile "$profile" "$claude_bin" plugin install \
      --scope user --yes ponytail@ponytail --json >/dev/null 2>&1 ||
      with_claude_profile "$profile" "$claude_bin" plugin update \
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
      --open-web-dashboard false
    CODEX_HOME="$profile" "$codex_bin" mcp add context7 -- \
      "$context7_bin" --transport stdio
  done

  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    for server in serena context7; do
      with_claude_profile "$profile" "$claude_bin" mcp remove \
        --scope user "$server" >/dev/null 2>&1 || true
    done
    with_claude_profile "$profile" "$claude_bin" mcp add --scope user serena -- \
      "$serena_bin" start-mcp-server --context=claude-code --project-from-cwd \
      --open-web-dashboard false
    with_claude_profile "$profile" "$claude_bin" mcp add --scope user context7 -- \
      "$context7_bin" --transport stdio
  done
}

install_headroom() {
  local uv_bin

  uv_bin="$(command -v uv)"
  if command -v headroom >/dev/null 2>&1 && [[ -f "$HOME/.headroom/deploy/default/manifest.json" ]]; then
    headroom install stop --profile default || return
  fi
  UV_TOOL_BIN_DIR="$HOME/.local/bin" "$uv_bin" tool install \
    --python "$PYTHON_VERSION" --upgrade 'headroom-ai[proxy,code]'
  # Dedup's 10-minute tracker expires before the 1-hour prompt cache.
  headroom install apply --preset persistent-service --scope provider \
    --providers manual --target claude --target codex --env HEADROOM_DEDUPE=0
  "$("$uv_bin" tool dir)/headroom-ai/bin/python" "$SCRIPT_DIR/agent_config.py" \
    headroom-work "$HOME/.claude-work" "$HOME/.codex-work"
}

install_global_agents() {
  local profile

  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/__AGENTS.md" "$profile/AGENTS.md"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/__AGENTS.md" "$profile/CLAUDE.md"
  done
}

install_codex_hooks() {
  local config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/codex/codex_compact_warning.py" "$SCRIPT_DIR/context7_version_guard.py" "$SCRIPT_DIR/codex/codex_rtk_hook.py" \
    "$config_dir/"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    agent_config codex-hooks "$profile/hooks.json" "$SCRIPT_DIR/codex/codex-hooks.json"
    agent_config codex-statusline "$profile/config.toml"
  done
}

install_claude_compact_statusline() {
  local config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/claude/claude_compact_statusline.py" \
    "$config_dir/claude_compact_statusline.py"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    agent_config statusline "$profile/settings.json"
  done
}

install_claude_context7_guard() {
  local config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/context7_version_guard.py" \
    "$config_dir/context7_version_guard.py"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    agent_config context7-guard "$profile/settings.json"
  done
}

install_idle_compact() {
  local config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/idle_compact.py" "$config_dir/idle_compact.py"
  mkdir -p "$HOME/.agents/skills/pitstop"
  install -m 0644 "$SCRIPT_DIR/codex/pitstop/SKILL.md" "$HOME/.agents/skills/pitstop/SKILL.md"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile/commands"
    install -m 0644 "$SCRIPT_DIR/claude/pitstop.md" "$profile/commands/pitstop.md"
    agent_config idle-compact "$profile/settings.json"
  done
}

disable_claude_attribution() {
  local profile

  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    agent_config attribution "$profile/settings.json"
  done
}

disable_claude_connectors() {
  local claude_bin listing profile

  claude_bin="$(type -P claude)"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    listing="$(with_claude_profile "$profile" "$claude_bin" mcp list 2>/dev/null || true)"
    agent_config connectors "$profile/settings.json" "$listing"
  done
}

install_shell_config() {
  local config_dir="$HOME/.config/dotfiles"

  mkdir -p "$config_dir"
  install -m 0644 "$SCRIPT_DIR/ai-install.sh" "$config_dir/ai-install.sh"
  if ! grep -q '^# BEGIN AI TOOLING$' "$HOME/.bashrc" 2>/dev/null; then
    cat "$SCRIPT_DIR/bashrc-snippet.sh" >> "$HOME/.bashrc"
  fi
}

echo "==> Installing AI command-line tools..."
install_ai_tools
echo "==> Installing VS Code commands..."
install_vscode_commands
echo "==> Installing global Codex and Claude instructions..."
install_global_agents
echo "==> Installing Codex Serena, Context7 guard and compact-warning hooks..."
install_codex_hooks
echo "==> Configuring RTK for Codex and Claude profiles..."
configure_rtk
echo "==> Installing Claude compact-warning status line..."
install_claude_compact_statusline
echo "==> Installing Claude Context7 version guard..."
install_claude_context7_guard
echo "==> Installing idle compaction hooks..."
install_idle_compact
echo "==> Disabling Claude commit and PR attribution..."
disable_claude_attribution
echo "==> Disabling unused claude.ai connectors in Claude profiles..."
disable_claude_connectors
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
echo "==> Run 'fabric --setup' once to select Fabric's AI provider."
echo "==> Review and trust RTK, Serena, Context7 and Ponytail hooks with /hooks in each Codex profile."
echo "==> Running LLM toolchain smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"
