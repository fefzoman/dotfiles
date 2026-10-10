#!/usr/bin/env python3
"""Edit and verify Codex and Claude profile config for ai-install.sh and smoke-test.sh."""

import json
import os
import re
import sys
import tomllib
from pathlib import Path

STATUSLINE = 'python3 "$HOME/.config/dotfiles/claude_compact_statusline.py"'
CONTEXT7_GUARD = 'python3 "$HOME/.config/dotfiles/context7_version_guard.py"'
IDLE_COMPACT = 'python3 "$HOME/.config/dotfiles/idle_compact.py"'
HEADROOM_URL = "http://127.0.0.1:8787"
SHELL_BEGIN = "# BEGIN AI TOOLING SHELL ENVIRONMENT"
SHELL_END = "# END AI TOOLING SHELL ENVIRONMENT"


def load(path: str) -> dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_toml(path: str) -> dict:
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def hook_entries(data: dict):
    for event, groups in data.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                yield event, group.get("matcher"), hook.get("type"), hook.get("command")


# Installer edits.


def codex_shell_path(config: str, path: str) -> None:
    config = Path(config)
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    text = re.sub(
        rf"\n?{re.escape(SHELL_BEGIN)}.*?{re.escape(SHELL_END)}\n?", "\n", text, flags=re.DOTALL
    )
    if re.search(r"(?m)^\s*(?:\[shell_environment_policy(?:\.|\])|shell_environment_policy\.)", text):
        raise SystemExit(f"{config} already defines shell_environment_policy; add {path!r} to its PATH")
    block = f"{SHELL_BEGIN}\n[shell_environment_policy]\nset = {{ PATH = {json.dumps(path)} }}\n{SHELL_END}\n"
    config.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")


def codex_hooks(target: str, required: str) -> None:
    data = load(target)
    events = data.setdefault("hooks", {})
    for event, groups in list(events.items()):
        for group in groups:
            group["hooks"] = [
                hook
                for hook in group.get("hooks", [])
                if not re.search(r"(?:^|/)serena-hooks\s+reset(?:\s|$)", hook.get("command") or "")
            ]
        events[event] = [group for group in groups if group.get("hooks")]
        if not events[event]:
            del events[event]

    for event, groups in load(required)["hooks"].items():
        installed_groups = events.setdefault(event, [])
        for required_group in groups:
            matcher = required_group.get("matcher")
            installed = next((g for g in installed_groups if g.get("matcher") == matcher), None)
            if installed is None:
                installed = {"hooks": []} if matcher is None else {"hooks": [], "matcher": matcher}
                installed_groups.append(installed)
            installed["hooks"] += [h for h in required_group["hooks"] if h not in installed["hooks"]]
    save(target, data)


def statusline(settings: str) -> None:
    data = load(settings)
    owned = {"type": "command", "command": STATUSLINE}
    if data.get("statusLine") not in (None, owned):
        print(f"Warning: preserving existing {settings} statusLine.", file=sys.stderr)
        return
    data["statusLine"] = owned
    save(settings, data)


def context7_guard(settings: str) -> None:
    data = load(settings)
    hooks = data.setdefault("hooks", {})
    hooks["PreToolUse"] = [
        entry
        for entry in hooks.get("PreToolUse", [])
        if all(hook.get("command") != CONTEXT7_GUARD for hook in entry.get("hooks", []))
    ] + [
        {
            "matcher": "mcp__context7__query-docs|mcp__claude_ai_Context7__query-docs",
            "hooks": [{"type": "command", "command": CONTEXT7_GUARD, "timeout": 5}],
        }
    ]
    save(settings, data)


def idle_compact(settings: str) -> None:
    data = load(settings)
    wanted = {
        "Stop": {"command": f"{IDLE_COMPACT} arm", "asyncRewake": True, "timeout": 4000},
        "UserPromptSubmit": {"command": f"{IDLE_COMPACT} guard", "timeout": 10},
    }
    hooks = data.setdefault("hooks", {})
    # Sweeping every event also drops hooks this installer no longer wants, such as the old SessionStart load.
    for event in list(hooks):
        hooks[event] = [
            entry
            for entry in hooks[event]
            if all(not str(h.get("command", "")).startswith(IDLE_COMPACT) for h in entry.get("hooks", []))
        ]
    for event, hook in wanted.items():
        hooks.setdefault(event, []).append({"hooks": [{"type": "command", **hook}]})
    save(settings, data)


def attribution(settings: str) -> None:
    data = load(settings)
    data["attribution"] = {"commit": "", "pr": ""}
    data.pop("includeCoAuthoredBy", None)
    save(settings, data)


def connectors(settings: str, listing: str) -> None:
    # Account-level claude.ai connectors can't be removed locally; server-wide deny rules drop their tools from context.
    used = {"Claude Docs", "Atlassian MCP"}
    names = re.findall(r"^claude\.ai (.+?): ", listing, re.MULTILINE)
    if not names:
        print(f"Warning: no claude.ai connectors listed; keeping {settings} deny rules.", file=sys.stderr)
        return
    data = load(settings)
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    deny[:] = [rule for rule in deny if not rule.startswith("mcp__claude_ai_")]
    deny += ["mcp__" + re.sub(r"[^A-Za-z0-9_-]", "_", f"claude.ai {n}") for n in names if n not in used]
    save(settings, data)


def headroom_work(claude_dir: str, codex_dir: str) -> None:
    # Runs under Headroom's own interpreter, the only one with these modules.
    import headroom.providers.claude.install as claude
    import headroom.providers.codex.install as codex
    from headroom.install.state import load_manifest

    manifest = load_manifest("default")
    claude.claude_settings_path = lambda: Path(claude_dir) / "settings.json"
    codex.codex_config_path = lambda: Path(codex_dir) / "config.toml"
    claude.apply_provider_scope(manifest)
    codex.apply_provider_scope(manifest)


# Smoke-test checks.


def policy_matches(source: str, target: str, rtk_file: str = "", rtk_reference: str = "") -> bool:
    target = Path(target)
    if not target.is_file():
        return False
    actual = target.read_text(encoding="utf-8")
    if rtk_file:
        reference = rtk_reference or f"@{rtk_file}"
        if not Path(rtk_file).is_file() or actual.count(reference) != 1:
            return False
        actual = actual.replace(reference, "")
    return actual.strip() == Path(source).read_text(encoding="utf-8").strip()


def codex_plugin_enabled() -> bool:
    return any(
        p.get("pluginId") == "ponytail@ponytail" and p.get("installed") and p.get("enabled")
        for p in json.load(sys.stdin).get("installed", [])
    )


def codex_mcp_enabled(name: str) -> bool:
    return any(s.get("name") == name and s.get("enabled") for s in json.load(sys.stdin))


def claude_plugin_enabled() -> bool:
    return any(p.get("id") == "ponytail@ponytail" and p.get("enabled", True) for p in json.load(sys.stdin))


def claude_hook_enabled(settings: str, command: str) -> bool:
    return any(entry[3] == command for entry in hook_entries(load(settings)))


def statusline_enabled(settings: str) -> bool:
    status = load(settings).get("statusLine", {})
    return status.get("type") == "command" and status.get("command") == STATUSLINE


def attribution_disabled(settings: str) -> bool:
    return load(settings).get("attribution") == {"commit": "", "pr": ""}


def claude_headroom(settings: str) -> bool:
    return load(settings).get("env", {}).get("ANTHROPIC_BASE_URL") == HEADROOM_URL


def codex_headroom(config: str) -> bool:
    config = load_toml(config)
    provider = config.get("model_providers", {}).get("headroom", {})
    return config.get("model_provider") == "headroom" and provider.get("base_url") == f"{HEADROOM_URL}/v1"


def codex_rtk_path(config: str, rtk_dir: str) -> bool:
    path = load_toml(config).get("shell_environment_policy", {}).get("set", {}).get("PATH", "")
    return rtk_dir in path.split(os.pathsep)


def codex_hooks_valid(required: str, installed: str) -> bool:
    installed = set(hook_entries(load(installed)))
    obsolete = any(command and "serena-hooks reset" in command for *_, command in installed)
    return set(hook_entries(load(required))) <= installed and not obsolete


COMMANDS = {
    command.__name__.replace("_", "-"): command
    for command in (
        codex_shell_path, codex_hooks, statusline, context7_guard, idle_compact, attribution,
        connectors, headroom_work, policy_matches, codex_plugin_enabled, codex_mcp_enabled,
        claude_plugin_enabled, claude_hook_enabled, statusline_enabled, attribution_disabled,
        claude_headroom, codex_headroom, codex_rtk_path, codex_hooks_valid,
    )
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} {{{','.join(COMMANDS)}}} ARGS...", file=sys.stderr)
        return 2
    return int(COMMANDS[sys.argv[1]](*sys.argv[2:]) is False)


if __name__ == "__main__":
    raise SystemExit(main())
