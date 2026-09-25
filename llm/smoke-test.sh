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

plugin_enabled_for_claude() {
  with_claude_profile "$1" claude plugin list --json 2>/dev/null |
    python -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(not any(p.get("id")=="ponytail@ponytail" and p.get("enabled", True) for p in data))'
}

mcp_enabled_for_claude() {
  with_claude_profile "$1" claude mcp get "$2" >/dev/null 2>&1
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

claude_statusline_enabled() {
  python - "$1/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1])
if not settings.is_file():
    raise SystemExit(1)
status = json.loads(settings.read_text(encoding="utf-8")).get("statusLine", {})
raise SystemExit(
    status.get("type") != "command"
    or status.get("command") != 'python3 "$HOME/.config/dotfiles/claude_compact_statusline.py"'
)
PY
}

claude_attribution_disabled() {
  python - "$1/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1])
data = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
raise SystemExit(data.get("attribution") != {"commit": "", "pr": ""})
PY
}

claude_routed_through_headroom() {
  python - "$1/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1])
data = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
raise SystemExit(data.get("env", {}).get("ANTHROPIC_BASE_URL") != "http://127.0.0.1:8787")
PY
}

codex_routed_through_headroom() {
  python - "$1/config.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

config = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
provider = config.get("model_providers", {}).get("headroom", {})
raise SystemExit(
    config.get("model_provider") != "headroom"
    or provider.get("base_url") != "http://127.0.0.1:8787/v1"
)
PY
}

codex_shell_path_has_rtk() {
  python - "$1/config.toml" "$(dirname "$(command -v rtk)")" <<'PY'
import os
import sys
import tomllib
from pathlib import Path

config = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
path = config.get("shell_environment_policy", {}).get("set", {}).get("PATH", "")
raise SystemExit(sys.argv[2] not in path.split(os.pathsep))
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

for command_name in python codex claude rtk headroom token-profiler node uv serena context7-mcp code code-work; do
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

if headroom install status >/dev/null 2>&1; then
  pass "Headroom persistent proxy is installed and healthy"
else
  fail "Headroom persistent proxy is not installed or not healthy"
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

if cmp -s "$SCRIPT_DIR/codex_compact_warning.py" \
  "$HOME/.config/dotfiles/codex_compact_warning.py"; then
  pass "Installed Codex compact-warning hook matches the repository"
else
  fail "Installed Codex compact-warning hook is missing or stale"
fi

if cmp -s "$SCRIPT_DIR/claude_compact_statusline.py" \
  "$HOME/.config/dotfiles/claude_compact_statusline.py"; then
  pass "Installed Claude compact-warning status line matches the repository"
else
  fail "Installed Claude compact-warning status line is missing or stale"
fi

if bash --noprofile --norc -c \
  'source "$1"; declare -F code >/dev/null; alias "??" >/dev/null; alias codex-work >/dev/null; alias claude-work >/dev/null; ! declare -F install_ai_tools >/dev/null' \
  _ "$HOME/.config/dotfiles/ai-install.sh"; then
  pass "Sourcing AI configuration loads functions without running the installer"
else
  fail "AI configuration source-only mode is broken"
fi

for profile in "$HOME/.codex" "$HOME/.codex-work"; do
  if cmp -s "$SCRIPT_DIR/codex-hooks.json" "$profile/hooks.json"; then
    pass "Codex compact-warning hook is configured in $profile"
  else
    warn "Codex compact-warning hook was not installed over existing hooks in $profile"
  fi

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

  if codex_routed_through_headroom "$profile"; then
    pass "Codex routes through Headroom in $profile"
  else
    fail "Codex bypasses Headroom in $profile"
  fi

  if codex_shell_path_has_rtk "$profile"; then
    pass "Codex command PATH includes RTK in $profile"
  else
    fail "Codex command PATH cannot resolve RTK in $profile"
  fi
done

for profile in "$HOME/.claude" "$HOME/.claude-work"; do
  if claude_statusline_enabled "$profile"; then
    pass "Claude compact-warning status line is enabled in $profile"
  else
    warn "Claude compact-warning status line is not enabled in $profile"
  fi

  if policy_matches "$profile/CLAUDE.md" "$profile/RTK.md" '@RTK.md'; then
    pass "Claude policy and RTK import are valid in $profile"
  else
    fail "Claude policy or RTK import is invalid in $profile"
  fi

  if claude_attribution_disabled "$profile"; then
    pass "Claude commit and PR attribution is disabled in $profile"
  else
    fail "Claude adds commit or PR attribution in $profile"
  fi

  if claude_routed_through_headroom "$profile"; then
    pass "Claude routes through Headroom in $profile"
  else
    fail "Claude bypasses Headroom in $profile"
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
