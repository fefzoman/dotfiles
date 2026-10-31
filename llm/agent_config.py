#!/usr/bin/env python3
"""Edit and verify Codex and Claude profile config for ai-install.sh and smoke-test.sh."""

import json
import os
import re
import sys
import tomllib
from pathlib import Path

STATUSLINE = 'python3 "$HOME/.config/dotfiles/claude_compact_statusline.py"'
CODEX_STATUSLINE = ["model-with-reasoning", "context-used", "used-tokens", "context-window-size", "five-hour-limit", "weekly-limit"]
CONTEXT7_GUARD = 'python3 "$HOME/.config/dotfiles/context7_version_guard.py"'
IDLE_COMPACT = 'python3 "$HOME/.config/dotfiles/idle_compact.py"'
READ_HINT = 'python3 "$HOME/.config/dotfiles/read_hint.py"'
HEADROOM_URL = "http://127.0.0.1:8787"
# ENABLE_TOOL_SEARCH was set by Headroom's install, whose revert drops it; keep tool loading unchanged.
CONTEXT_TRIM_ENV = {"CLAUDE_CODE_DISABLE_ARTIFACT": "1", "ENABLE_TOOL_SEARCH": "true"}
CONTEXT_TRIM_SKILLS = {
    **dict.fromkeys(("docs", "docx", "pptx", "xlsx", "pdf", "google-workspace", "morning", "import-memory", "skill-creator"), "off"),
    **dict.fromkeys(("dataviz", "claude-api", "claude-in-chrome", "schedule", "run", "plugin-authoring", "keybindings-help",
                     "fewer-permission-prompts"), "user-invocable-only"),
}
# Cheapest setting passing every trial in benchmarks/claude_matrix and benchmarks/codex_matrix.
EFFORT = "medium"
WORK_PLUGINS = ("dlm@dlm-user",)
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
    expected = tomllib.loads(text)
    env = expected.setdefault("shell_environment_policy", {}).setdefault("set", {})
    env["PATH"] = path
    # Codex can reorder tables and leave the old markers in reverse order.
    text = re.sub(rf"(?m)^(?:{re.escape(SHELL_BEGIN)}|{re.escape(SHELL_END)})\n?", "", text)
    subtable = re.search(r"(?m)^\[shell_environment_policy\.set\][^\n]*\n", text)
    table = subtable or re.search(r"(?m)^\[shell_environment_policy\][^\n]*\n", text)
    if table:
        end = re.search(r"(?m)^\s*\[", text[table.end():])
        stop = table.end() + end.start() if end else len(text)
        key = "PATH" if subtable else "set"
        value = json.dumps(path) if subtable else "{ " + ", ".join(
            f"{json.dumps(k)} = {json.dumps(v)}" for k, v in env.items()) + " }"
        line = f"{key} = {value}\n"
        body, count = re.subn(rf"(?m)^[ \t]*{key}[ \t]*=[^\n]*\n?", lambda _: line, text[table.end():stop])
        text = text[:table.end()] + (body if count else line + body) + text[stop:]
    else:
        text = text.rstrip() + f"\n\n[shell_environment_policy]\nset = {{ PATH = {json.dumps(path)} }}\n"
    if tomllib.loads(text) != expected:
        raise SystemExit(f"{config}: set shell_environment_policy.set.PATH manually; unsupported TOML layout")
    config.write_text(text, encoding="utf-8")


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
            commands = {h["command"] for h in required_group["hooks"]}
            for group in installed_groups:
                if group.get("matcher") == matcher:
                    group["hooks"] = [h for h in group["hooks"] if h.get("command") not in commands]
            installed["hooks"] += required_group["hooks"]
        events[event] = [group for group in installed_groups if group.get("hooks")]
    save(target, data)


def codex_statusline(config: str) -> None:
    path = Path(config)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = tomllib.loads(text)
    if "status_line" in data.get("tui", {}):
        previous = CODEX_STATUSLINE[1:]
        if data["tui"]["status_line"] not in (previous, [item for item in previous if item != "used-tokens"]):
            return
        text = re.sub(r'(?m)^([ \t]*status_line[ \t]*=[ \t]*)\[[^\]]*\]',
                      lambda match: match[1] + json.dumps(CODEX_STATUSLINE), text, count=1)
        if tomllib.loads(text)["tui"]["status_line"] != CODEX_STATUSLINE:
            raise SystemExit(f"{config}: update the existing tui status_line to {CODEX_STATUSLINE}")
        path.write_text(text, encoding="utf-8")
        return
    setting = "status_line = " + json.dumps(CODEX_STATUSLINE) + "\n"
    table = re.search(r"(?m)^\s*\[tui\][ \t]*(?:#.*)?$", text)
    if table:
        text = text[:table.end()] + "\n" + setting + text[table.end():]
    elif subtable := re.search(r"(?m)^[ \t]*\[tui\.", text):
        text = text[:subtable.start()] + "[tui]\n" + setting + "\n" + text[subtable.start():]
    elif "tui" not in data:
        text = text.rstrip() + "\n\n[tui]\n" + setting
    try:
        installed = tomllib.loads(text)["tui"].get("status_line")
    except tomllib.TOMLDecodeError:
        installed = None
    if installed != CODEX_STATUSLINE:
        raise SystemExit(f"{config}: add {setting.strip()} to the existing tui configuration")
    path.write_text(text, encoding="utf-8")


def effort(settings: str) -> None:
    data = load(settings)
    data["effortLevel"] = EFFORT
    save(settings, data)


def codex_effort(config: str) -> None:
    path = Path(config)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    first_table = re.search(r"(?m)^[ \t]*\[", text)
    top, tables = (text[:first_table.start()], text[first_table.start():]) if first_table else (text, "")
    line = f"model_reasoning_effort = {json.dumps(EFFORT)}"
    top, found = re.subn(r"(?m)^[ \t]*model_reasoning_effort[ \t]*=.*$", line, top)
    text = (top if found else line + "\n" + top) + tables
    if tomllib.loads(text).get("model_reasoning_effort") != EFFORT:
        raise SystemExit(f"{config}: set {line} at the top level")
    path.write_text(text, encoding="utf-8")


def statusline(settings: str) -> None:
    data = load(settings)
    owned = {"type": "command", "command": STATUSLINE}
    if data.get("statusLine") not in (None, owned):
        print(f"Warning: preserving existing {settings} statusLine.", file=sys.stderr)
        return
    data["statusLine"] = owned
    save(settings, data)


def pre_tool_hook(settings: str, matcher: str, command: str) -> None:
    data = load(settings)
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault("PreToolUse", [])
    for entry in groups:
        entry["hooks"] = [hook for hook in entry.get("hooks", []) if hook.get("command") != command]
    hooks["PreToolUse"] = [entry for entry in groups if entry["hooks"]] + [
        {"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 5}]}]
    save(settings, data)


def scope_plugins(agent: str, profile: str) -> None:
    if agent not in {"codex", "claude"}:
        raise ValueError(f"Unknown agent: {agent}")
    profile = Path(profile)
    if profile.name != f".{agent}":
        return
    if agent == "claude":
        path = str(profile / "settings.json")
        data = load(path)
        data.setdefault("enabledPlugins", {}).update(dict.fromkeys(WORK_PLUGINS, False))
        save(path, data)
        return
    path = profile / "config.toml"
    text = path.read_text() if path.exists() else ""
    expected = tomllib.loads(text)
    for plugin in WORK_PLUGINS:
        table = expected.setdefault("plugins", {}).setdefault(plugin, {})
        if table.get("enabled") is False:
            continue
        table["enabled"] = False
        pattern = rf'(?ms)^(\[plugins\.(?:"{re.escape(plugin)}"|\'{re.escape(plugin)}\')\][^\n]*\n)(.*?)(?=^\[|\Z)'
        section = re.search(pattern, text)
        if section:
            body, count = re.subn(r"(?m)^[ \t]*enabled[ \t]*=.*$", "enabled = false", section[2])
            text = text[:section.start()] + section[1] + (body if count else "enabled = false\n" + body) + text[section.end():]
        else:
            text = text.rstrip() + f"\n\n[plugins.{json.dumps(plugin)}]\nenabled = false\n"
    if tomllib.loads(text) != expected:
        raise SystemExit(f"{path}: scope platform plugins manually; unsupported TOML layout")
    path.write_text(text)


def context7_guard(settings: str) -> None:
    pre_tool_hook(settings, "mcp__context7__query-docs|mcp__claude_ai_Context7__query-docs", CONTEXT7_GUARD)


def read_hint(settings: str) -> None:
    pre_tool_hook(settings, "Read|Bash", READ_HINT)


def idle_compact(settings: str) -> None:
    data = load(settings)
    wanted = {
        "Stop": {"hooks": [{"type": "command", "command": f"{IDLE_COMPACT} arm", "asyncRewake": True, "timeout": 4000}]},
        "UserPromptSubmit": {"hooks": [{"type": "command", "command": f"{IDLE_COMPACT} guard", "timeout": 10}]},
        "SessionStart": {"matcher": "clear", "hooks": [{"type": "command", "command": f"{IDLE_COMPACT} clear", "timeout": 10}]},
        "SessionEnd": {"hooks": [{"type": "command", "command": f"{IDLE_COMPACT} end", "timeout": 30}]},
        "PostToolUse": {"matcher": "Edit|MultiEdit|Write",
                        "hooks": [{"type": "command", "command": f"{IDLE_COMPACT} instructions", "timeout": 5}]},
    }
    hooks = data.setdefault("hooks", {})
    # Sweeping every event also drops hooks this installer no longer wants.
    for event in list(hooks):
        for entry in hooks[event]:
            entry["hooks"] = [h for h in entry.get("hooks", [])
                              if not str(h.get("command", "")).startswith(IDLE_COMPACT)]
        hooks[event] = [entry for entry in hooks[event] if entry["hooks"]]
    for event, entry in wanted.items():
        hooks.setdefault(event, []).append(entry)
    save(settings, data)


def attribution(settings: str) -> None:
    data = load(settings)
    data["attribution"] = {"commit": "", "pr": ""}
    data.pop("includeCoAuthoredBy", None)
    save(settings, data)


def connectors(settings: str, listing: str) -> None:
    # Account-level claude.ai connectors can't be removed locally; server-wide deny rules drop their tools from context.
    used = {"Atlassian MCP"}
    names = re.findall(r"^claude\.ai (.+?): ", listing, re.MULTILINE)
    if not names:
        print(f"Warning: no claude.ai connectors listed; keeping {settings} deny rules.", file=sys.stderr)
        return
    data = load(settings)
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    deny[:] = [rule for rule in deny if not rule.startswith("mcp__claude_ai_")]
    deny += ["mcp__" + re.sub(r"[^A-Za-z0-9_-]", "_", f"claude.ai {n}") for n in names if n not in used]
    save(settings, data)


def context_trim(settings: str) -> None:
    data = load(settings)
    data.setdefault("env", {}).update(CONTEXT_TRIM_ENV)
    data.setdefault("skillOverrides", {}).update(CONTEXT_TRIM_SKILLS)
    save(settings, data)


def context_efficiency(agent: str, profile: str) -> None:
    if agent not in {"codex", "claude"}:
        raise ValueError(f"Unknown agent: {agent}")
    profile = Path(profile)
    plugins = ("superpowers@openai-curated", "superpowers@superpowers-dev", "superpowers@claude-plugins-official")
    if agent == "codex":
        path = profile / "config.toml"
        text = path.read_text() if path.exists() else ""
        expected = tomllib.loads(text)
        changes = [("skills", "max_context_tokens", 2000)] + [
            (f"plugins.{json.dumps(plugin)}", "enabled", False) for plugin in plugins[:2]]
        for section, key, value in changes:
            if section == "skills":
                table = expected.setdefault("skills", {})
            else:
                table = expected.setdefault("plugins", {}).setdefault(json.loads(section[8:]), {})
            table[key] = value
            line = f"{key} = {json.dumps(value)}\n"
            match = re.search(rf"(?ms)^\[{re.escape(section)}\][^\n]*\n(.*?)(?=^\[|\Z)", text)
            if match:
                body, count = re.subn(rf"(?m)^[ \t]*{key}[ \t]*=.*\n?", line, match[1])
                text = text[:match.start(1)] + (body if count else line + body) + text[match.end(1):]
            else:
                text = text.rstrip() + f"\n\n[{section}]\n{line}"
        if tomllib.loads(text) != expected:
            raise SystemExit(f"{path}: unsupported TOML layout; no changes written")
        path.write_text(text)
    else:
        path = profile / "settings.json"
        data = load(str(path))
        data.setdefault("env", {})["SLASH_COMMAND_TOOL_CHAR_BUDGET"] = "8000"
        data.setdefault("enabledPlugins", {}).update(dict.fromkeys(plugins[1:], False))
        save(str(path), data)
    path = profile / ("hooks.json" if agent == "codex" else "settings.json")
    data = load(str(path))
    for event, groups in list(data.get("hooks", {}).items()):
        for group in groups:
            group["hooks"] = [h for h in group.get("hooks", []) if not re.search(
                r"(?:^|/)serena-hooks\s+(?:activate|remind|reset)(?:\s|$)", h.get("command") or "")]
        data["hooks"][event] = [g for g in groups if g.get("hooks")]
    save(str(path), data)


def context_efficient(agent: str, profile: str) -> bool:
    profile = Path(profile)
    if agent == "codex":
        data = load_toml(str(profile / "config.toml"))
        return data.get("skills", {}).get("max_context_tokens") == 2000 and all(
            data.get("plugins", {}).get(plugin, {}).get("enabled") is False
            for plugin in ("superpowers@openai-curated", "superpowers@superpowers-dev"))
    data = load(str(profile / "settings.json"))
    return data.get("env", {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET") == "8000" and all(
        data.get("enabledPlugins", {}).get(plugin) is False
        for plugin in ("superpowers@superpowers-dev", "superpowers@claude-plugins-official"))


def headroom_unroute(claude_dir: str, codex_dir: str) -> None:
    # Runs under Headroom's interpreter: only its revert hands Codex threads back to the native provider.
    from headroom.install.models import ManagedMutation
    from headroom.providers.codex.install import revert_provider_scope

    settings = Path(claude_dir) / "settings.json"
    data = load(settings)
    if data.get("env", {}).get("ANTHROPIC_BASE_URL") == HEADROOM_URL:
        del data["env"]["ANTHROPIC_BASE_URL"]
        save(settings, data)
    revert_provider_scope(ManagedMutation("codex", "toml-block", str(Path(codex_dir) / "config.toml")), None)


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


def codex_plugin_enabled(plugin_id: str = "ponytail@ponytail", *alternatives: str) -> bool:
    return any(
        p.get("pluginId") in (plugin_id, *alternatives) and p.get("installed") and p.get("enabled")
        for p in json.load(sys.stdin).get("installed", [])
    )


def codex_mcp_enabled(name: str) -> bool:
    return any(s.get("name") == name and s.get("enabled") for s in json.load(sys.stdin))


def claude_plugin_enabled(plugin_id: str = "ponytail@ponytail", *alternatives: str) -> bool:
    return any(p.get("id") in (plugin_id, *alternatives) and p.get("enabled", True) for p in json.load(sys.stdin))


def claude_hook_enabled(settings: str, command: str) -> bool:
    return any(entry[3] == command for entry in hook_entries(load(settings)))


def statusline_enabled(settings: str) -> bool:
    status = load(settings).get("statusLine", {})
    return status.get("type") == "command" and status.get("command") == STATUSLINE


def attribution_disabled(settings: str) -> bool:
    return load(settings).get("attribution") == {"commit": "", "pr": ""}


def context_trimmed(settings: str) -> bool:
    data = load(settings)
    return CONTEXT_TRIM_ENV.items() <= data.get("env", {}).items() and CONTEXT_TRIM_SKILLS.items() <= data.get("skillOverrides", {}).items()


def claude_direct(settings: str) -> bool:
    return load(settings).get("env", {}).get("ANTHROPIC_BASE_URL") != HEADROOM_URL


def codex_direct(config: str) -> bool:
    config = load_toml(config)
    return config.get("model_provider") != "headroom" and "headroom" not in config.get("model_providers", {})


def codex_rtk_path(config: str, rtk_dir: str) -> bool:
    path = load_toml(config).get("shell_environment_policy", {}).get("set", {}).get("PATH", "")
    return rtk_dir in path.split(os.pathsep)


def codex_hooks_valid(required: str, installed: str) -> bool:
    entries = list(hook_entries(load(installed)))
    installed = set(entries)
    obsolete = any(command and "serena-hooks reset" in command for *_, command in installed)
    return len(entries) == len(installed) and set(hook_entries(load(required))) <= installed and not obsolete


def hooks_unique(settings: str) -> bool:
    entries = list(hook_entries(load(settings)))
    return len(entries) == len(set(entries))


def plugins_scoped(agent: str, profile: str) -> bool:
    profile = Path(profile)
    if profile.name != f".{agent}":
        return True
    if agent == "codex":
        plugins = load_toml(str(profile / "config.toml")).get("plugins", {})
        return all(plugins.get(plugin, {}).get("enabled") is False for plugin in WORK_PLUGINS)
    plugins = load(str(profile / "settings.json")).get("enabledPlugins", {})
    return all(plugins.get(plugin) is False for plugin in WORK_PLUGINS)


COMMANDS = {
    command.__name__.replace("_", "-"): command
    for command in (
        codex_shell_path, codex_hooks, codex_statusline, codex_effort, effort, read_hint, statusline, context7_guard, idle_compact, attribution, scope_plugins,
        connectors, context_trim, context_efficiency, context_efficient, headroom_unroute, policy_matches, codex_plugin_enabled, codex_mcp_enabled,
        claude_plugin_enabled, claude_hook_enabled, statusline_enabled, attribution_disabled,
        context_trimmed, claude_direct, codex_direct, codex_rtk_path, codex_hooks_valid, hooks_unique, plugins_scoped,
    )
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} {{{','.join(COMMANDS)}}} ARGS...", file=sys.stderr)
        return 2
    return int(COMMANDS[sys.argv[1]](*sys.argv[2:]) is False)


if __name__ == "__main__":
    raise SystemExit(main())
