#!/usr/bin/env bash
set -uo pipefail

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STRICT=0
PASSES=0
WARNINGS=0
FAILURES=0

usage() {
  echo "Usage: $0 [--strict]" >&2
  exit 2
}

case "${1:-}" in
  "") ;;
  --strict) STRICT=1 ;;
  *) usage ;;
esac
(( $# <= 1 )) || usage

pass() {
  PASSES=$((PASSES + 1))
  printf 'PASS  %s\n' "$1"
}

warn() {
  WARNINGS=$((WARNINGS + 1))
  printf 'WARN  %s\n' "$1"
}

fail() {
  FAILURES=$((FAILURES + 1))
  printf 'FAIL  %s\n' "$1"
}

check() {
  local ok="$1" bad="$2"
  shift 2

  if "$@" >/dev/null 2>&1; then
    pass "$ok"
  else
    fail "$bad"
  fi
}

agent_config() {
  python "$SCRIPT_DIR/agent_config.py" "$@"
}

# The default profile runs without CLAUDE_CONFIG_DIR, as the VS Code extension does.
with_claude_profile() {
  local profile="$1"
  shift
  if [[ "$profile" == "$HOME/.claude" ]]; then
    env -u CLAUDE_CONFIG_DIR "$@"
  else
    CLAUDE_CONFIG_DIR="$profile" "$@"
  fi
}

codex_plugin_enabled() {
  CODEX_HOME="$1" command codex plugin list --json | agent_config codex-plugin-enabled "${@:2}"
}

codex_mcp_enabled() {
  CODEX_HOME="$1" command codex mcp list --json | agent_config codex-mcp-enabled "$2"
}

claude_plugin_enabled() {
  with_claude_profile "$1" claude plugin list --json | agent_config claude-plugin-enabled "${@:2}"
}

claude_mcp_enabled() {
  with_claude_profile "$1" claude mcp get "$2"
}

echo "LLM toolchain smoke test"
echo "========================"

for command_name in python codex claude fabric rtk headroom token-profiler node uv serena specify context7-mcp code code-work; do
  check "$command_name is available" "$command_name is missing" \
    command -v "$command_name"
done

check "Codex starts" "Codex failed to start" codex --version
check "Claude Code starts" "Claude Code failed to start" claude --version
check "Spec Kit starts" "Spec Kit failed to start" specify version
check "Headroom persistent proxy is installed and healthy" \
  "Headroom persistent proxy is not installed or not healthy" \
  headroom install status
check "Token profiler starts with tiktoken" "Token profiler failed to start" \
  token-profiler --version

for profile in codex codex-work claude claude-work; do
  check "Token profiler accepts the $profile profile" "Token profiler rejected the $profile profile" \
    token-profiler "$profile" --help
done

for file in ai-install.sh codex/codex_compact_warning.py idle_compact.py context7_version_guard.py \
  claude/claude_compact_statusline.py; do
  check "Installed $file matches the repository" "Installed $file is missing or stale" \
    cmp -s "$SCRIPT_DIR/$file" "$HOME/.config/dotfiles/${file##*/}"
done

check "Codex pitstop skill matches the repository" "Codex pitstop skill is missing or stale" \
  cmp -s "$SCRIPT_DIR/codex/pitstop/SKILL.md" "$HOME/.agents/skills/pitstop/SKILL.md"

check "Sourcing AI configuration loads functions without running the installer" \
  "AI configuration source-only mode is broken" \
  bash --noprofile --norc -c \
  'source "$1"; declare -F code >/dev/null; declare -F codex >/dev/null; declare -F __codex_answer >/dev/null; alias "??" >/dev/null; alias codex-work >/dev/null; alias claude-work >/dev/null; ! declare -F install_ai_tools >/dev/null' \
  _ "$HOME/.config/dotfiles/ai-install.sh"

rtk_dir="$(dirname "$(command -v rtk)")"
check "RTK produces valid Codex rewrites and respects bypasses" "RTK Codex hook contract is invalid" \
  python -m unittest discover -s "$SCRIPT_DIR/codex" -p test_codex_rtk_hook.py
for profile in "$HOME/.codex" "$HOME/.codex-work"; do
  check "Codex RTK, Serena, Context7 guard and compact-warning hooks are configured in $profile" \
    "Codex RTK, Serena, Context7 guard or compact-warning hooks are invalid in $profile" \
    agent_config codex-hooks-valid "$SCRIPT_DIR/codex/codex-hooks.json" "$profile/hooks.json"
  check "Codex policy and RTK import are valid in $profile" \
    "Codex policy or RTK import is invalid in $profile" \
    agent_config policy-matches "$SCRIPT_DIR/codex/__AGENTS.md" "$profile/AGENTS.md" "$profile/RTK.md"
  check "Ponytail is installed and enabled in $profile" "Ponytail is missing or disabled in $profile" \
    codex_plugin_enabled "$profile"
  check "Superpowers is installed and enabled in $profile" "Superpowers is missing or disabled in $profile" \
    codex_plugin_enabled "$profile" superpowers@openai-curated superpowers@superpowers-dev
  check "Codex routes through Headroom in $profile" "Codex bypasses Headroom in $profile" \
    agent_config codex-headroom "$profile/config.toml"
  check "Codex command PATH includes RTK in $profile" "Codex command PATH cannot resolve RTK in $profile" \
    agent_config codex-rtk-path "$profile/config.toml" "$rtk_dir"
done

for profile in "$HOME/.claude" "$HOME/.claude-work"; do
  if agent_config statusline-enabled "$profile/settings.json"; then
    pass "Claude compact-warning status line is enabled in $profile"
  else
    warn "Claude compact-warning status line is not enabled in $profile"
  fi

  check "Claude policy and RTK import are valid in $profile" \
    "Claude policy or RTK import is invalid in $profile" \
    agent_config policy-matches "$SCRIPT_DIR/claude/__AGENTS.md" "$profile/CLAUDE.md" "$profile/RTK.md" '@RTK.md'
  check "Claude commit and PR attribution is disabled in $profile" \
    "Claude adds commit or PR attribution in $profile" \
    agent_config attribution-disabled "$profile/settings.json"
  check "Claude routes through Headroom in $profile" "Claude bypasses Headroom in $profile" \
    agent_config claude-headroom "$profile/settings.json"
  check "RTK command hook is enabled in $profile" "RTK command hook is missing in $profile" \
    agent_config claude-hook-enabled "$profile/settings.json" "rtk hook claude"
  for sub in arm guard clear; do
    check "Idle compaction $sub hook is enabled in $profile" "Idle compaction $sub hook is missing in $profile" \
      agent_config claude-hook-enabled "$profile/settings.json" \
      "python3 \"\$HOME/.config/dotfiles/idle_compact.py\" $sub"
  done
  check "/pitstop command matches the repository in $profile" "/pitstop command is missing or stale in $profile" \
    cmp -s "$SCRIPT_DIR/claude/pitstop.md" "$profile/commands/pitstop.md"
  check "Context7 version guard is enabled in $profile" "Context7 version guard is missing in $profile" \
    agent_config claude-hook-enabled "$profile/settings.json" 'python3 "$HOME/.config/dotfiles/context7_version_guard.py"'
  check "Ponytail is installed and enabled in $profile" "Ponytail is missing or disabled in $profile" \
    claude_plugin_enabled "$profile"
  check "Superpowers is installed and enabled in $profile" "Superpowers is missing or disabled in $profile" \
    claude_plugin_enabled "$profile" superpowers@claude-plugins-official superpowers@superpowers-dev
done

for server in serena context7; do
  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    check "$server MCP is enabled in $profile" "$server MCP is not enabled in $profile" \
      codex_mcp_enabled "$profile" "$server"
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    check "$server MCP is enabled in $profile" "$server MCP is not enabled in $profile" \
      claude_mcp_enabled "$profile" "$server"
  done
done

echo "------------------------"
printf 'Result: %d passed, %d warnings, %d failed\n' "$PASSES" "$WARNINGS" "$FAILURES"
echo "No model or API requests were made."

if (( FAILURES > 0 || STRICT == 1 && WARNINGS > 0 )); then
  exit 1
fi
