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

require_command() {
  local command_name="$1"

  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name is available"
  else
    fail "$command_name is missing"
  fi
}

policy_matches() {
  local target="$1"
  local rtk_file="${2:-}"
  local rtk_reference="${3:-}"

  python - "$SCRIPT_DIR/AGENTS.md" "$target" "$rtk_file" "$rtk_reference" <<'PY'
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
target = Path(sys.argv[2])
if not target.is_file():
    raise SystemExit(1)

actual = target.read_text(encoding="utf-8")
if sys.argv[3]:
    if not Path(sys.argv[3]).is_file():
        raise SystemExit(1)
    reference = sys.argv[4] or f"@{sys.argv[3]}"
    if actual.count(reference) != 1:
        raise SystemExit(1)
    actual = actual.replace(reference, "")

raise SystemExit(actual.strip() != source)
PY
}

plugin_enabled() {
  CODEX_HOME="$1" command codex plugin list --json 2>/dev/null |
    python -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(not any(p.get("pluginId")=="ponytail@ponytail" and p.get("installed") and p.get("enabled") for p in data.get("installed", [])))'
}

mcp_enabled_for_codex() {
  local profile="$1"
  local server="$2"

  CODEX_HOME="$profile" command codex mcp list --json 2>/dev/null |
    python -c 'import json,sys; name=sys.argv[1]; raise SystemExit(not any(s.get("name")==name and s.get("enabled") for s in json.load(sys.stdin)))' "$server"
}

plugin_enabled_for_claude() {
  local profile

  profile="$1"
  CLAUDE_CONFIG_DIR="$profile" command claude plugin list --json 2>/dev/null |
    python -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(not any(p.get("id")=="ponytail@ponytail" and p.get("enabled", True) for p in data))'
}

mcp_enabled_for_claude() {
  CLAUDE_CONFIG_DIR="$1" command claude mcp get "$2" >/dev/null 2>&1
}

rtk_hook_enabled_for_claude() {
  python - "$1/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1])
if not settings.is_file():
    raise SystemExit(1)

hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
commands = (
    hook.get("command")
    for event in hooks.values()
    for group in event
    for hook in group.get("hooks", [])
)
raise SystemExit("rtk hook claude" not in commands)
PY
}

check_mcp() {
  local profile server

  server="$1"

  for profile in "$HOME/.codex" "$HOME/.codex-work"; do
    if mcp_enabled_for_codex "$profile" "$server"; then
      pass "$server MCP is enabled in $profile"
    else
      fail "$server MCP is not enabled in $profile"
    fi
  done
  for profile in "$HOME/.claude" "$HOME/.claude-work"; do
    if mcp_enabled_for_claude "$profile" "$server"; then
      pass "$server MCP is enabled in $profile"
    else
      fail "$server MCP is not enabled in $profile"
    fi
  done
}

echo "LLM toolchain smoke test"
echo "========================"

for command_name in python codex claude rtk headroom token-profiler node uv serena context7-mcp; do
  require_command "$command_name"
done

if codex --version >/dev/null 2>&1; then
  pass "Codex starts"
else
  fail "Codex failed to start"
fi

if claude --version >/dev/null 2>&1; then
  pass "Claude Code starts"
else
  fail "Claude Code failed to start"
fi

if headroom wrap codex --help >/dev/null 2>&1; then
  pass "Headroom exposes the Codex wrapper"
else
  fail "Headroom Codex wrapper is unavailable"
fi

if headroom wrap claude --help >/dev/null 2>&1; then
  pass "Headroom exposes the Claude wrapper"
else
  fail "Headroom Claude wrapper is unavailable"
fi

if token-profiler --version >/dev/null 2>&1; then
  pass "Token profiler starts with tiktoken"
else
  fail "Token profiler failed to start"
fi

for profile in codex codex-work claude claude-work; do
  if token-profiler "$profile" --help >/dev/null 2>&1; then
    pass "Token profiler accepts the $profile profile"
  else
    fail "Token profiler rejected the $profile profile"
  fi
done

if cmp -s "$SCRIPT_DIR/ai-install.sh" "$HOME/.config/dotfiles/ai-install.sh"; then
  pass "Installed AI shell configuration matches the repository"
else
  fail "Installed AI shell configuration is missing or stale"
fi

if bash --noprofile --norc -c \
  'source "$1"; declare -F codex >/dev/null; declare -F claude >/dev/null; declare -F code-work >/dev/null; alias "??" >/dev/null; alias codex-work >/dev/null; alias claude-work >/dev/null; ! declare -F install_ai_tools >/dev/null' \
  _ "$HOME/.config/dotfiles/ai-install.sh"; then
  pass "Sourcing AI configuration loads functions without running the installer"
else
  fail "AI configuration source-only mode is broken"
fi

for profile in "$HOME/.codex" "$HOME/.codex-work"; do
  if policy_matches "$profile/AGENTS.md" "$profile/RTK.md"; then
    pass "Codex policy and RTK import are valid in $profile"
  else
    fail "Codex policy or RTK import is invalid in $profile"
  fi

  if plugin_enabled "$profile"; then
    pass "Ponytail is installed and enabled in $profile"
  else
    fail "Ponytail is missing or disabled in $profile"
  fi
done

for profile in "$HOME/.claude" "$HOME/.claude-work"; do
  if policy_matches "$profile/CLAUDE.md" "$profile/RTK.md" '@RTK.md'; then
    pass "Claude policy and RTK import are valid in $profile"
  else
    fail "Claude policy or RTK import is invalid in $profile"
  fi

  if rtk_hook_enabled_for_claude "$profile"; then
    pass "RTK command hook is enabled in $profile"
  else
    fail "RTK command hook is missing in $profile"
  fi

  if plugin_enabled_for_claude "$profile"; then
    pass "Ponytail is installed and enabled in $profile"
  else
    fail "Ponytail is missing or disabled in $profile"
  fi
done

check_mcp serena
check_mcp context7

echo "------------------------"
printf 'Result: %d passed, %d warnings, %d failed\n' "$PASSES" "$WARNINGS" "$FAILURES"
echo "No model or API requests were made."

if (( FAILURES > 0 || STRICT == 1 && WARNINGS > 0 )); then
  exit 1
fi
