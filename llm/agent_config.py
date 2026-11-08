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
RETIRED_CONTEXT7_GUARD = 'python3 "$HOME/.config/dotfiles/context7_version_guard.py"'
IDLE_COMPACT = 'python3 "$HOME/.config/dotfiles/idle_compact.py"'
OBSOLETE_CODEX_HOOK = r"(?:^|/)serena-hooks(?:\s|$)|idle_compact\.py\"?\s+clear$"
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
PONYTAIL = "ponytail@ponytail"
SHELL_BEGIN = "# BEGIN AI TOOLING SHELL ENVIRONMENT"
SHELL_END = "# END AI TOOLING SHELL ENVIRONMENT"
PERMISSIONS_BEGIN = "# BEGIN AI TOOLING CODEX PERMISSIONS"
PERMISSIONS_END = "# END AI TOOLING CODEX PERMISSIONS"


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


def remove_legacy_hooks(target: str) -> None:
    data = load(target)
    if isinstance(data.get("description"), str):
        data["description"] = data["description"].replace("Serena session cleanup, ", "")
        data["description"] = data["description"].replace("Context7 CLI version guard, ", "")
    events = data.get("hooks", {})
    for event, groups in list(events.items()):
        for group in groups:
            group["hooks"] = [
                hook
                for hook in group.get("hooks", [])
                if not re.search(OBSOLETE_CODEX_HOOK, hook.get("command") or "")
                and hook.get("command") != RETIRED_CONTEXT7_GUARD
            ]
        events[event] = [group for group in groups if group.get("hooks")]
        if not events[event]:
            del events[event]

    save(target, data)


def codex_hooks(target: str, required: str) -> None:
    remove_legacy_hooks(target)
    data = load(target)
    events = data.setdefault("hooks", {})
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


def codex_permissions(config: str) -> None:
    path = Path(config)
    text = path.read_text() if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    expected = tomllib.loads(text)
    defaults = {"sandbox_mode": "workspace-write", "approval_policy": "never", "default_permissions": "dotfiles"}
    expected.update(defaults)
    expected.setdefault("sandbox_workspace_write", {})["network_access"] = True
    first_table = re.search(r"(?m)^[ \t]*\[", text)
    top, tables = (text[:first_table.start()], text[first_table.start():]) if first_table else (text, "")
    for key, value in defaults.items():
        line = f"{key} = {json.dumps(value)}\n"
        top, found = re.subn(rf"(?m)^[ \t]*{key}[ \t]*=[^\n]*\n?", line, top)
        if not found:
            top = line + top
    text = top + tables
    table = re.search(r"(?m)^\[sandbox_workspace_write\][ \t]*(?:#.*)?\n", text)
    if table:
        end = re.search(r"(?m)^[ \t]*\[", text[table.end():])
        stop = table.end() + end.start() if end else len(text)
        body, found = re.subn(r"(?m)^[ \t]*network_access[ \t]*=[^\n]*\n?", "network_access = true\n", text[table.end():stop])
        text = text[:table.end()] + (body if found else "network_access = true\n" + body) + text[stop:]
    else:
        text = text.rstrip() + "\n\n[sandbox_workspace_write]\nnetwork_access = true\n"
    filesystem = dict.fromkeys(("~/.codex", "~/.codex-work", "~/.config/dotfiles"), "write")
    workspace = expected["sandbox_workspace_write"]
    filesystem.update(dict.fromkeys(workspace.get("writable_roots", []), "write"))
    for key, special in (("exclude_tmpdir_env_var", ":tmpdir"), ("exclude_slash_tmp", ":slash_tmp")):
        if workspace.get(key):
            filesystem[special] = "read"
    filesystem[":workspace_roots"] = {".git": "write"}
    profile = {"extends": ":workspace", "filesystem": filesystem, "network": {"enabled": True}}
    expected.setdefault("permissions", {})["dotfiles"] = profile
    block = '[permissions.dotfiles]\nextends = ":workspace"\n\n[permissions.dotfiles.filesystem]\n'
    block += "".join(f"{json.dumps(key)} = {json.dumps(value)}\n"
                     for key, value in filesystem.items() if key != ":workspace_roots")
    block += '\n[permissions.dotfiles.filesystem.\":workspace_roots\"]\n\".git\" = \"write\"\n'
    block += '\n[permissions.dotfiles.network]\nenabled = true\n'
    text = re.sub(rf"(?ms)^{re.escape(PERMISSIONS_BEGIN)}\n.*?^{re.escape(PERMISSIONS_END)}\n?", "", text)
    text = text.rstrip() + f"\n\n{PERMISSIONS_BEGIN}\n{block}{PERMISSIONS_END}\n"
    if tomllib.loads(text) != expected:
        raise SystemExit(f"{config}: set sandbox defaults manually; unsupported TOML layout")
    path.write_text(text)


def claude_permissions(settings: str) -> None:
    data = load(settings)
    permissions = data.setdefault("permissions", {})
    permissions.update(defaultMode="dontAsk", blockWritesOutsideWorkingDirectories=True)
    allow = permissions.setdefault("allow", [])
    allow += [tool for tool in ("Edit", "Write", "NotebookEdit") if tool not in allow]
    sandbox = data.setdefault("sandbox", {})
    sandbox.update(enabled=True, failIfUnavailable=True, autoAllowBashIfSandboxed=True,
                   allowUnsandboxedCommands=False, excludedCommands=[])
    filesystem = sandbox.setdefault("filesystem", {})
    filesystem["disabled"] = False
    writable = filesystem.setdefault("allowWrite", [])
    writable += [root for root in ("~/.claude", "~/.claude-work", "~/.config/dotfiles") if root not in writable]
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


def codex_model_instructions(config: str, instructions: str) -> None:
    instructions = Path(instructions).resolve(strict=True)
    if not instructions.read_text(encoding="utf-8").strip():
        raise SystemExit(f"{instructions}: model instructions must not be empty")
    path = Path(config)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    expected = tomllib.loads(text)
    expected["model_instructions_file"] = str(instructions)
    first_table = re.search(r"(?m)^[ \t]*\[", text)
    top, tables = (text[:first_table.start()], text[first_table.start():]) if first_table else (text, "")
    line = f"model_instructions_file = {json.dumps(str(instructions))}\n"
    top, found = re.subn(r"(?m)^[ \t]*model_instructions_file[ \t]*=[^\n]*\n?", lambda _: line, top)
    text = (top if found else line + top) + tables
    if tomllib.loads(text) != expected:
        raise SystemExit(f"{config}: set model_instructions_file manually; unsupported TOML layout")
    path.write_text(text, encoding="utf-8")


def codex_model_instructions_valid(config: str, source: str) -> bool:
    installed = load_toml(config).get("model_instructions_file")
    return bool(installed and Path(installed).is_file()
                and Path(installed).read_bytes() == Path(source).read_bytes())


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


def remove_context7_path(config: str) -> None:
    path = Path(config)
    if not path.exists():
        return
    current = load_toml(config).get("shell_environment_policy", {}).get("set", {}).get("PATH")
    retired = str(Path.home() / ".codex-work/context7-cli/node_modules/.bin")
    if current is not None and retired in current.split(os.pathsep):
        codex_shell_path(config, os.pathsep.join(p for p in current.split(os.pathsep) if p != retired))


def read_hint(settings: str) -> None:
    pre_tool_hook(settings, "Read|Bash", READ_HINT)


def idle_compact(settings: str) -> None:
    data = load(settings)
    wanted = {
        "Stop": {"hooks": [{"type": "command", "command": f"{IDLE_COMPACT} arm", "async": True, "timeout": 4000}]},
        "UserPromptSubmit": {"hooks": [{"type": "command", "command": f"{IDLE_COMPACT} guard", "timeout": 10}]},
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
        changes = [("skills", "max_context_tokens", 2000), ("skills", "include_instructions", False)] + [
            (f"plugins.{json.dumps(plugin)}", "enabled", False) for plugin in plugins[:2]] + [
            (f"plugins.{json.dumps(PONYTAIL)}", "enabled", True)]
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
        data.setdefault("enabledPlugins", {}).update(dict.fromkeys(plugins[1:], False), **{PONYTAIL: True})
        save(str(path), data)
    path = profile / ("hooks.json" if agent == "codex" else "settings.json")
    remove_legacy_hooks(str(path))


def context_efficient(agent: str, profile: str) -> bool:
    profile = Path(profile)
    if agent == "codex":
        data = load_toml(str(profile / "config.toml"))
        skills = data.get("skills", {})
        plugins = data.get("plugins", {})
        return skills.get("max_context_tokens") == 2000 and skills.get("include_instructions") is False and all(
            plugins.get(plugin, {}).get("enabled") is False
            for plugin in ("superpowers@openai-curated", "superpowers@superpowers-dev")
        ) and plugins.get(PONYTAIL, {}).get("enabled") is True
    data = load(str(profile / "settings.json"))
    plugins = data.get("enabledPlugins", {})
    return data.get("env", {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET") == "8000" and all(
        plugins.get(plugin) is False for plugin in ("superpowers@superpowers-dev", "superpowers@claude-plugins-official")
    ) and plugins.get(PONYTAIL) is True


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


def claude_mcp_paths(profile: Path) -> list[Path]:
    return ([profile.parent / ".claude.json", profile / ".claude.json"]
            if profile.name == ".claude" else [profile / ".claude.json"])


def remove_claude_retrieval_mcps(profile: str) -> None:
    for path in claude_mcp_paths(Path(profile)):
        if not path.is_file():
            continue
        data = load(str(path))
        before = json.dumps(data)
        for entry in [data, *data.get("projects", {}).values()]:
            for name in ("serena", "context7"):
                entry.get("mcpServers", {}).pop(name, None)
        if json.dumps(data) != before:
            save(str(path), data)


def retrieval_mcps_absent(agent: str, profile: str, server: str = "") -> bool:
    profile = Path(profile)
    names = {server} if server else {"serena", "context7"}
    if agent == "codex":
        path = profile / "config.toml"
        return not names.intersection((load_toml(str(path)) if path.exists() else {}).get("mcp_servers", {}))
    if agent != "claude":
        raise ValueError(f"Unknown agent: {agent}")
    return all(not names.intersection(entry.get("mcpServers", {}))
               for path in claude_mcp_paths(profile) for data in [load(str(path))]
               for entry in [data, *data.get("projects", {}).values()])


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
    obsolete = any((command and re.search(OBSOLETE_CODEX_HOOK, command))
                   or command == RETIRED_CONTEXT7_GUARD
                   for _, matcher, _, command in installed)
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
        codex_shell_path, codex_hooks, remove_legacy_hooks, remove_context7_path, codex_statusline, codex_effort, codex_permissions, codex_model_instructions, codex_model_instructions_valid, claude_permissions, effort, read_hint, statusline, idle_compact, attribution, scope_plugins,
        connectors, context_trim, context_efficiency, context_efficient, headroom_unroute, policy_matches, codex_plugin_enabled, codex_mcp_enabled, retrieval_mcps_absent, remove_claude_retrieval_mcps,
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
