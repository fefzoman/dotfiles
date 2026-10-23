#!/usr/bin/env bash

export RTK_TELEMETRY_DISABLED=1
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

codex() {
  command codex --dangerously-bypass-hook-trust "$@"
}

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

warn_live_sessions() {
  local answer=""

  # Upgrades and hook, MCP or skill edits change the prompt prefix open sessions resume with.
  pgrep -f '(^|/)(claude|codex)( |$)' >/dev/null || return 0
  echo "Warning: Claude or Codex sessions are running; resuming them after this install rebuilds their prompt cache." >&2
  [[ -t 0 ]] || return 0
  read -r -p "Continue? [y/N] " answer || true
  [[ "$answer" == [yY]* ]] || exit 1
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
  UV_TOOL_BIN_DIR="$HOME/.local/bin" "$(type -P uv)" tool install \
    --python "$PYTHON_VERSION" --reinstall "$SCRIPT_DIR/smart-read"
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

install_superpowers() {
  local claude_bin codex_bin profile

  codex_bin="$(type -P codex)"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    if CODEX_HOME="$profile" "$codex_bin" plugin list --json |
      agent_config codex-plugin-enabled superpowers@openai-curated superpowers@superpowers-dev; then
      echo "==> Superpowers already enabled for $profile"
      continue
    fi
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace add obra/superpowers --json >/dev/null || return
    CODEX_HOME="$profile" "$codex_bin" plugin marketplace upgrade superpowers-dev --json >/dev/null || return
    CODEX_HOME="$profile" "$codex_bin" plugin add superpowers@superpowers-dev --json >/dev/null || return
    echo "==> Superpowers installed for $profile"
  done

  claude_bin="$(type -P claude)"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    if with_claude_profile "$profile" "$claude_bin" plugin list --json |
      agent_config claude-plugin-enabled superpowers@claude-plugins-official superpowers@superpowers-dev; then
      echo "==> Superpowers already enabled for $profile"
      continue
    fi
    with_claude_profile "$profile" "$claude_bin" plugin marketplace add \
      anthropics/claude-plugins-official >/dev/null 2>&1 ||
      with_claude_profile "$profile" "$claude_bin" plugin marketplace update \
        claude-plugins-official >/dev/null || return
    with_claude_profile "$profile" "$claude_bin" plugin install \
      --scope user --yes superpowers@claude-plugins-official --json >/dev/null || return
    echo "==> Superpowers installed for $profile"
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

remove_headroom() {
  local python uv_bin

  uv_bin="$(command -v uv)"
  python="$("$uv_bin" tool dir)/headroom-ai/bin/python"
  [[ -x "$python" ]] || return 0
  # Unroute every profile while Headroom's modules still exist: its Codex revert also
  # moves threads back to the native provider's history menu.
  "$python" "$SCRIPT_DIR/agent_config.py" headroom-unroute "$HOME/.claude" "$HOME/.codex"
  "$python" "$SCRIPT_DIR/agent_config.py" headroom-unroute "$HOME/.claude-work" "$HOME/.codex-work"
  if [[ -f "$HOME/.headroom/deploy/default/manifest.json" ]]; then
    headroom install remove --profile default || headroom install remove --profile default || return
  fi
  "$uv_bin" tool uninstall headroom-ai
}

remove_speckit() {
  rm -rf "$HOME/.agents/skills/speckit-init"
  rm -f "$HOME/.claude/commands/speckit-init.md" "$HOME/.claude-work/commands/speckit-init.md"
  if "$(type -P uv)" tool list | grep -q '^specify-cli '; then
    "$(type -P uv)" tool uninstall specify-cli
  fi
}

install_global_agents() {
  local profile

  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/codex/__AGENTS.md" "$profile/AGENTS.md"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile/commands"
    install -m 0644 "$SCRIPT_DIR/claude/__AGENTS.md" "$profile/CLAUDE.md"
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
    agent_config codex-effort "$profile/config.toml"
  done
}

install_claude_hook() {
  local script="$1" setting="$2" config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/$script" "$config_dir/"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    agent_config "$setting" "$profile/settings.json"
  done
}

install_idle_compact() {
  local config_dir="$HOME/.config/dotfiles" name profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/idle_compact.py" "$config_dir/idle_compact.py"
  for name in pitstop checkpoint; do
    mkdir -p "$HOME/.agents/skills/$name"
    install -m 0644 "$SCRIPT_DIR/codex/$name/SKILL.md" "$HOME/.agents/skills/$name/SKILL.md"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile/commands"
    install -m 0644 "$SCRIPT_DIR/claude/pitstop.md" "$SCRIPT_DIR/claude/checkpoint.md" "$profile/commands/"
    agent_config idle-compact "$profile/settings.json"
  done
}

configure_claude_settings() {
  local claude_bin listing profile

  claude_bin="$(type -P claude)"
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile"
    listing="$(with_claude_profile "$profile" "$claude_bin" mcp list 2>/dev/null || true)"
    agent_config attribution "$profile/settings.json"
    agent_config connectors "$profile/settings.json" "$listing"
    agent_config context-trim "$profile/settings.json"
    agent_config effort "$profile/settings.json"
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

warn_live_sessions
echo "==> Installing AI command-line tools..."
install_ai_tools
echo "==> Removing Headroom from Codex and Claude profiles..."
remove_headroom
echo "==> Removing Spec Kit..."
remove_speckit
echo "==> Installing VS Code commands..."
install_vscode_commands
echo "==> Installing global Codex and Claude instructions..."
install_global_agents
echo "==> Installing Codex Serena, Context7 guard and compact-warning hooks..."
install_codex_hooks
echo "==> Configuring RTK for Codex and Claude profiles..."
configure_rtk
echo "==> Installing Claude compact-warning status line..."
install_claude_hook claude/claude_compact_statusline.py statusline
echo "==> Installing Claude Context7 version guard..."
install_claude_hook context7_version_guard.py context7-guard
echo "==> Installing idle compaction hooks..."
install_idle_compact
echo "==> Installing smart-read hints for large whole-file reads..."
install_claude_hook read_hint.py read-hint
echo "==> Disabling Claude attribution and unused claude.ai connectors, trimming context, setting effort..."
configure_claude_settings
echo "==> Installing Ponytail for Codex and Claude profiles..."
install_ponytail
echo "==> Installing Superpowers for Codex and Claude profiles..."
install_superpowers
echo "==> Configuring Serena and Context7 for Codex and Claude profiles..."
configure_agent_mcps
echo "==> Installing Codex and Claude token profiler..."
bash "$SCRIPT_DIR/token-profiler/install.sh"
echo "==> Installing AI shell configuration..."
install_shell_config
echo "==> Run 'fabric --setup' once to select Fabric's AI provider."
echo "==> Codex shell commands bypass hook trust; Claude user and plugin hooks run by default."
echo "==> Running LLM toolchain smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"
