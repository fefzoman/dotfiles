#!/usr/bin/env bash

export RTK_TELEMETRY_DISABLED=1
export TRANSFORMERS_VERBOSITY=error
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

unset -f codex

code() {
  env -u CLAUDE_CONFIG_DIR CODEX_HOME="$HOME/.codex" code "$@"
}

# Claude has no persistent setting for this; the VS Code extension keeps the default prompt.
claude() {
  local prompt="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-prompt.md" arg
  for arg; do [[ "$arg" == --system-prompt* ]] && prompt=""; done
  if [[ -n "$prompt" && -f "$prompt" ]]; then
    command claude --system-prompt-file "$prompt" "$@"
  else
    command claude "$@"
  fi
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

if (( $# > 1 )) || [[ -n "${1:-}" && "${1:-}" != --retrieval-only && "${1:-}" != --docs-only ]]; then
  echo "Usage: $0 [--retrieval-only | --docs-only]" >&2
  exit 2
fi

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
  [[ -t 0 ]] || { echo "Stop running agents before an unattended install." >&2; return 1; }
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

  remove_retired_retrieval_tools
  curl -fsSL https://claude.ai/install.sh | bash -s latest
  curl -fsSL https://raw.githubusercontent.com/danielmiessler/Fabric/main/scripts/installer/install.sh |
    env INSTALL_DIR="$HOME/.local/bin" bash
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

remove_retired_retrieval_tools() {
  local profile prefix config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
  [[ "$config_home" == /* ]] || config_home="$HOME/.config"
  prefix="$(npm prefix --global)"
  [[ "$prefix" == /* ]] || { echo "Cannot determine the global npm prefix." >&2; return 1; }
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    agent_config remove-context7-path "$profile/config.toml"
  done
  npm uninstall --global --prefix "$HOME/.local" ctx7 @upstash/context7-mcp
  if [[ "$prefix" != "$HOME/.local" ]]; then
    npm uninstall --global --prefix "$prefix" ctx7 @upstash/context7-mcp
  fi
  rm -rf -- "$HOME/.codex-work/context7-cli" "$config_home/context7" "$HOME/.context7"
  if command -v uv >/dev/null 2>&1; then
    if uv tool list | grep -q '^serena-agent '; then
      UV_TOOL_BIN_DIR="$HOME/.local/bin" uv tool uninstall serena-agent
    fi
    uv cache clean serena-agent
  fi
  rm -rf -- "$HOME/.serena"
}

remove_retrieval_mcps() {
  local codex_bin profile server
  codex_bin="$(type -P codex)"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    for server in serena context7; do
      if ! agent_config retrieval-mcps-absent codex "$profile" "$server"; then
        CODEX_HOME="$profile" "$codex_bin" mcp remove "$server"
      fi
    done
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    agent_config remove-claude-retrieval-mcps "$profile"
  done
}

install_global_agents() {
  local profile skill
  local skills=(natural-article code-retrieval)
  [[ "${1:-}" != --retrieval-only ]] || skills=(code-retrieval)

  # Partial modes skip configure_rtk, so they restore its RTK import themselves.
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    install -m 0644 "$SCRIPT_DIR/codex/__AGENTS.md" "$profile/AGENTS.md"
    if [[ -n "${1:-}" && -f "$profile/RTK.md" ]]; then
      printf '\n@%s/RTK.md\n' "$profile" >> "$profile/AGENTS.md"
    fi
    if [[ -z "${1:-}" ]]; then
      install -m 0644 "$SCRIPT_DIR/codex-model-instructions.md" "$profile/model-instructions.md"
      agent_config codex-model-instructions "$profile/config.toml" "$profile/model-instructions.md"
    fi
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    mkdir -p "$profile/commands"
    install -m 0644 "$SCRIPT_DIR/claude/__AGENTS.md" "$profile/CLAUDE.md"
    if [[ -n "${1:-}" && -f "$profile/RTK.md" ]]; then
      printf '\n@RTK.md\n' >> "$profile/CLAUDE.md"
    fi
    if [[ -z "${1:-}" ]]; then
      install -m 0644 "$SCRIPT_DIR/claude-system-prompt.md" "$profile/system-prompt.md"
    fi
  done
  for profile in "$HOME/.codex" "$HOME/.codex-work" "$HOME/.claude" "$HOME/.claude-work"; do
    for skill in "${skills[@]}"; do
      mkdir -p "$profile/skills/$skill"
      install -m 0644 "$SCRIPT_DIR/skills/$skill/SKILL.md" "$profile/skills/$skill/SKILL.md"
      if [[ -d "$SCRIPT_DIR/skills/$skill/references" ]]; then
        mkdir -p "$profile/skills/$skill/references"
        install -m 0644 "$SCRIPT_DIR/skills/$skill/references/"*.md "$profile/skills/$skill/references/"
      fi
    done
  done
}

scope_platform_plugins() {
  agent_config scope-plugins codex "$HOME/.codex"
  agent_config scope-plugins claude "$HOME/.claude"
}

install_codex_hooks() {
  local config_dir="$HOME/.config/dotfiles" profile

  mkdir -p "$config_dir"
  install -m 0755 "$SCRIPT_DIR/codex/codex_compact_warning.py" "$SCRIPT_DIR/codex/codex_rtk_hook.py" \
    "$config_dir/"
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    mkdir -p "$profile"
    agent_config codex-hooks "$profile/hooks.json" "$SCRIPT_DIR/codex/codex-hooks.json"
    agent_config codex-statusline "$profile/config.toml"
    agent_config codex-effort "$profile/config.toml"
    agent_config codex-permissions "$profile/config.toml"
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
    agent_config claude-permissions "$profile/settings.json"
  done
}

configure_context_efficiency() {
  local agent profile
  for agent in codex claude; do
    for profile in "$HOME/.$agent" "$HOME/.$agent-work"; do
      agent_config context-efficiency "$agent" "$profile" || return
    done
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

if [[ "${1:-}" == --retrieval-only ]]; then
  warn_live_sessions || exit 1
  remove_retired_retrieval_tools
  remove_retrieval_mcps
  install_global_agents --retrieval-only
  for agent in codex claude; do
    for profile in "$HOME/.$agent" "$HOME/.$agent-work"; do
      if [[ "$agent" == codex ]]; then
        agent_config remove-legacy-hooks "$profile/hooks.json"
      else
        agent_config remove-legacy-hooks "$profile/settings.json"
      fi
    done
  done
  rm -f -- "$HOME/.config/dotfiles/context7_version_guard.py"
  mkdir -p "$HOME/.config/dotfiles"
  install -m 0644 "$SCRIPT_DIR/ai-install.sh" "$HOME/.config/dotfiles/ai-install.sh"
  for agent in codex claude; do
    for profile in "$HOME/.$agent" "$HOME/.$agent-work"; do
      agent_config retrieval-mcps-absent "$agent" "$profile" || exit 1
    done
  done
  exit 0
fi

if [[ "${1:-}" == --docs-only ]]; then
  warn_live_sessions || exit 1
  install_global_agents --docs-only
  exit 0
fi

warn_live_sessions || exit 1
echo "==> Installing AI command-line tools..."
install_ai_tools
echo "==> Installing VS Code commands..."
install_vscode_commands
echo "==> Installing global Codex and Claude instructions..."
install_global_agents
echo "==> Installing Codex command and compact-warning hooks..."
install_codex_hooks
echo "==> Configuring RTK for Codex and Claude profiles..."
configure_rtk
echo "==> Installing Claude compact-warning status line..."
install_claude_hook claude/claude_compact_statusline.py statusline
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
echo "==> Keeping platform plugins in work profiles; preserving work plugin selections..."
scope_platform_plugins
echo "==> Removing legacy retrieval MCP servers from Codex and Claude profiles..."
remove_retrieval_mcps
echo "==> Limiting startup context and making Superpowers opt-in..."
configure_context_efficiency || exit 1
rm -f -- "$HOME/.config/dotfiles/context7_version_guard.py"
echo "==> Installing Codex and Claude token profiler..."
bash "$SCRIPT_DIR/token-profiler/install.sh"
echo "==> Installing AI shell configuration..."
install_shell_config
echo "==> Run 'fabric --setup' once to select Fabric's AI provider."
echo "==> Review new or changed Codex hooks in /hooks; Claude user and plugin hooks run by default."
echo "==> Running LLM toolchain smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"
