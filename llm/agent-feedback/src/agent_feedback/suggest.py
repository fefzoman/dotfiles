"""Turn a finding's evidence into concrete changes, each naming its target and the evidence behind it."""

from collections import Counter, defaultdict
import shutil

BOTH = "CLAUDE.md and AGENTS.md"
LIMIT = 5
EXPLORE_TOOLS = {"Read", "Grep", "Glob"}
EDIT_TOOLS = {"Edit", "Write", "apply_patch"}
ERROR_HINTS = {
    "permission": "check sandbox and file permissions; do not bypass approvals",
    "missing_file": "verify the path exists from the working directory",
    "timeout": "narrow the command or raise its timeout",
    "usage": "check the installed version's --help for the right arguments",
    "test_failure": "read the first failing assertion and rerun only that test",
}
OUTPUT_FIXES = {
    "Read": "pass offset/limit and read only the needed range",
    "Grep": "narrow the path or glob and cap the results",
    "Bash": "filter the output (rtk, `| head`, `--stat`, quiet flags) or save it to a file and read the relevant part",
}
TURN_FIXES = {
    "failing": ("environment", "Turns dominated by failing calls: fix the failing prerequisite first (see the failure findings)."),
    "remote": ("instructions", "Remote-system investigations (cloud CLIs, containers, polling): turn the recurring queries "
                               f"into a documented script or skill referenced from {BOTH}, so a session runs one command."),
    "loop": ("instructions", "Edit-and-rerun loops: run the narrowest check and read the first failure before the next edit; "
                             f"document that check in {BOTH}."),
    "exploring": ("instructions", "Exploration-heavy turns: keep a codebase map and entry points in "
                                  f"{BOTH}, name files in the request, or delegate the search to a subagent."),
    "large": ("request", "Broad turns: split the request into smaller steps or agree on a plan first."),
}


def failed(row):
    return row["event_type"] == "tool.failed" or row["tool"].get("outcome") == "failure"


def item(target, change, rows, **extra):
    return {"target": target, "change": change, "incidents": len(rows),
            "tokens": sum(row["tool"].get("tokens") or 0 for row in rows), **extra}


def grouped(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return groups.items()


def detail(row, key):
    return row.get("local", {}).get(key)


def missing_executable(rows):
    for name, group in grouped(rows, lambda row: detail(row, "executable")):
        if name in (None, "(unusual name)"):
            yield item("environment", "Rerun `agent-feedback scan --details` to name the missing executables.", group)
        elif shutil.which(name):
            yield item("environment", f"`{name}` is on this shell's PATH now; if agents still miss it, "
                                      f"document its setup (venv, `uv run`, PATH) in {BOTH}.", group)
        else:
            yield item("environment", f"`{name}` is not on PATH: install it or document the supported "
                                      f"replacement in {BOTH}.", group)


def repeated_command_failure(rows):
    first = rows[0].get("local", {})
    command = f"`{first['command']}`" if "command" in first else "The same command"
    hint = ERROR_HINTS.get(first.get("error"), "read the first failure's message")
    yield item("environment", f"{command} failed {len(rows)} times unchanged: {hint} before retrying.", rows)


def oversized_output(rows):
    for (tool, command), group in grouped(rows, lambda row: (row["tool"].get("name"), detail(row, "command"))):
        subject = f"`{command}`" if command else f"{tool} calls" if tool != "other" else "MCP and other tool calls"
        fix = OUTPUT_FIXES.get(tool, "request a smaller result (filters, paging, fewer fields)")
        yield item("instructions", f"{subject}: {fix}.", group)


def repeated_read(rows):
    def key(row):
        where = detail(row, "where")
        return where, None if where in ("tool_output", "task_output") else detail(row, "path")
    for (where, path), group in grouped(rows, key):
        if where == "tool_output":
            yield item("instructions", "Saved tool outputs were re-read: search the saved file for the needed part "
                                       "instead of reading it again.", group)
        elif where == "task_output":
            yield item("instructions", "Background task output was re-read while it ran: wait for the completion "
                                       "notification or a monitor instead of polling the file.", group)
        elif where == "outside":
            subject = f"`{path}` (outside the working directory)" if path else "Files outside the working directory"
            yield item("instructions", f"{subject} re-read ({len(group)}x): keep the first read in view and re-read "
                                       "only after the file changes.", group)
        elif path:
            yield item("instructions", f"`{path}` was re-read ({len(group)}x): describe it in the codebase map "
                                       f"in {BOTH} or keep the first read in view.", group)
        else:
            yield item("instructions", "Rerun `agent-feedback scan --details` to name the re-read files.", group)


def turn_kind(calls):
    """Thresholds are tuned on local transcripts; ordered from most to least specific cause."""
    total = len(calls)
    families = Counter(detail(row, "family") for row in calls)
    if sum(map(failed, calls)) * 3 >= total:
        return "failing"
    if (families["remote"] + families["wait"]) * 5 >= total * 2:
        return "remote"
    if (sum(row["tool"].get("name") in EXPLORE_TOOLS for row in calls) + families["read"]) * 2 >= total:
        return "exploring"
    edits = sum(row["tool"].get("name") in EDIT_TOOLS for row in calls)
    repeats = max(Counter(row["tool"]["command_fingerprint"] for row in calls
                          if row["tool"].get("command_fingerprint")).values(), default=0)
    if edits and (repeats >= 5 or (edits * 10 >= total and families["run"] * 10 >= total)):
        return "loop"
    return "large"


def long_turn(rows):
    kinds = defaultdict(lambda: [0, []])
    for _, calls in grouped(rows, lambda row: (row["session_id"], row.get("turn_id"))):
        kind = kinds[turn_kind(calls)]
        kind[0] += 1
        kind[1].extend(calls)
    for kind, (turns, calls) in kinds.items():
        target, change = TURN_FIXES[kind]
        yield item(target, change, calls, turns=turns)


RULES = {function.__name__: function for function in
         (missing_executable, repeated_command_failure, oversized_output, repeated_read, long_turn)}


def suggest(rule, evidence):
    if rule not in RULES:
        return []
    return sorted(RULES[rule](evidence), key=lambda row: (-row["tokens"], -row["incidents"]))[:LIMIT]
