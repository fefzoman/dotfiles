"""Evidence-linked rules, not assertions about agent intent or task correctness."""

from collections import defaultdict

from .hooks import fingerprint
from .suggest import suggest

OVERSIZED_BYTES = 20_000
LONG_TURN_CALLS = 50
EVIDENCE_LINES = 10
SUGGESTION_LINES = 15
RULES = {
    "missing_executable": {
        "category": "environment", "classification": "suspected_cause",
        "description": "Shell results indicate an unavailable executable or exit status 127.",
        "recommendation": "Check the repository's documented runtime and dependency setup; "
                          "confirm the supported command before retrying. A subprocess can also exit 127.",
        "instruction": "Before running project tools, use the repository's documented runtime and "
                       "dependency setup. If a command reports an unavailable executable, check the "
                       "documented command and active environment before retrying it unchanged. "
                       "Do not install dependencies or change permissions without authorization.",
    },
    "repeated_command_failure": {
        "category": "unknown", "classification": "suspected_waste",
        "description": "The same command has at least three failed attempts without observed recovery in a session.",
        "recommendation": "Inspect the first failure and verify prerequisites before retrying the same command. "
                          "Confirm that retries were not an intentional experiment or flaky-test investigation.",
        "instruction": "After repeated failures of an unchanged command, inspect the first failure and "
                       "verify the documented prerequisites before retrying. Prefer a targeted diagnostic "
                       "check; keep deliberate retry experiments explicit and never hide failing checks.",
    },
    "permission_friction": {
        "category": "permissions", "classification": "observation",
        "description": "At least three approval requests were observed in a session; denials are not inferred.",
        "recommendation": "Review task scope with the user. Do not bypass approvals, relax sandbox rules, "
                          "or treat a denied request as agent incompetence.",
    },
    "repeated_read": {
        "category": "context", "classification": "suspected_waste",
        "description": "The same file range was read again in a session without an edit to that file in between.",
        "recommendation": "Keep the first read's content in view instead of re-reading it. "
                          "A re-read after context compaction or an outside change is legitimate.",
        "instruction": "Reuse file contents already read in this session; re-read a file only after it changed "
                       "or after the context was compacted.",
    },
    "oversized_output": {
        "category": "context", "classification": "suspected_waste",
        "description": f"A tool result exceeded {OVERSIZED_BYTES // 1000} KB, and every later model call re-sends it.",
        "recommendation": "Narrow searches, page through large files and filter or summarize command output "
                          "before it reaches the context.",
        "instruction": "Keep tool output small: bound searches and reads to the needed range and filter noisy "
                       "command output; save large logs to a file and read only the relevant part.",
    },
    "long_turn": {
        "category": "workflow", "classification": "observation",
        "description": f"A single user turn needed more than {LONG_TURN_CALLS} tool calls.",
        "recommendation": "Check whether the task was underspecified, the agent explored too broadly, "
                          "or a loop went unnoticed. Large legitimate tasks also produce long turns.",
    },
    "collection_gap": {
        "category": "tooling", "classification": "unverifiable_outcome",
        "description": "The collector recorded rejected or missing telemetry.",
        "recommendation": "Check adapter compatibility, message limits and local storage health. "
                          "Do not infer task failure or successful validation from missing telemetry.",
    },
}


def reference(event):
    return {key: event[key] for key in ("installation_id", "provider", "repository_id", "session_id", "event_id")}


def analyze(events):
    calls, terminal, auxiliary = {}, {}, defaultdict(list)
    for event in events:
        key = tuple(event.get(field) for field in ("installation_id", "provider", "repository_id", "session_id"))
        call = (*key, event.get("span_id", event["event_id"]))
        kind = event["event_type"]
        if kind == "tool.started":
            calls[call] = event.get("tool", {})
        elif kind in ("tool.completed", "tool.failed"):
            terminal[call] = {**event, "tool": {**calls.get(call, {}), **event.get("tool", {})}}
        elif kind in ("permission.requested", "collector.gap"):
            auxiliary[(kind, key)].append(event)
    groups, attempts, reads, turns = defaultdict(list), defaultdict(list), defaultdict(set), defaultdict(list)
    for event in terminal.values():
        tool = event.get("tool", {})
        repo = event["repository_id"]
        session = (event["installation_id"], event["provider"], event["session_id"])
        command = tool.get("command_fingerprint")
        failed = event["event_type"] == "tool.failed" or tool.get("outcome") == "failure"
        missing = tool.get("error_family") == "missing_executable" or (tool.get("name") == "Bash" and tool.get("exit_code") == 127)
        if missing and (failed or tool.get("outcome") == "unknown"):
            groups[(repo, "missing_executable", command)].append(event)
        if command:
            attempts[(repo, session, command)].append(event)
        path, target = (repo, session, tool.get("path_fingerprint")), tool.get("target_fingerprint")
        if tool.get("name") in ("Edit", "Write"):
            reads.pop(path, None)
        elif target and not failed:
            if target in reads[path]:
                groups[(repo, "repeated_read", None)].append(event)
            reads[path].add(target)
        if tool.get("output_bytes", 0) > OVERSIZED_BYTES:
            groups[(repo, "oversized_output", None)].append(event)
        if event.get("turn_id"):
            turns[(repo, session, event["turn_id"])].append(event)
    for (repo, _, _), calls in turns.items():
        if len(calls) > LONG_TURN_CALLS:
            groups[(repo, "long_turn", None)].extend(calls)
    for (repo, _, command), history in attempts.items():
        failures = []
        for event in history:
            if event["tool"].get("outcome") == "success":
                failures = []
            elif event["event_type"] == "tool.failed" or event["tool"].get("outcome") == "failure":
                failures.append(event)
        if len(failures) >= 3:
            groups[(repo, "repeated_command_failure", command)].extend(failures)
    for (kind, key), evidence in auxiliary.items():
        if kind == "collector.gap" or len(evidence) >= 3:
            rule = "collection_gap" if kind == "collector.gap" else "permission_friction"
            groups[(key[2], rule, None)].extend(evidence)
    findings = []
    for (repo, rule, command), evidence in sorted(groups.items(), key=lambda item: str(item[0])):
        spec = RULES[rule]
        sessions = {(row["installation_id"], row["provider"], row["session_id"]) for row in evidence}
        issue = "ISSUE-" + fingerprint(f"{repo}:{rule}:{command}")[:16]
        findings.append({
            "issue_id": issue, "repository_id": repo, "rule": rule,
            **{key: spec[key] for key in ("category", "classification", "description", "recommendation")},
            "command_fingerprint": command, "incidents": len(evidence), "sessions": len(sessions),
            "cost": cost(evidence),
            "providers": sorted({row["provider"] for row in evidence}),
            "suggestions": suggest(rule, evidence),
            "evidence": [reference(row) for row in evidence],
            "task_outcome": "unknown", "coverage": "metadata_only",
            "eligible_for_draft": "instruction" in spec and len(evidence) >= 3 and len(sessions) >= 2,
            "limitations": ["Signals do not establish an instruction defect or avoidable waste.",
                            "Ordering, policy/environment versions and task intent may be missing.",
                            "No correctness, regression or causal improvement has been established."],
        })
    return sorted(findings, key=lambda row: -(row["cost"]["tokens"] or 0))


def cost(evidence):
    """Tokens of the replies that issued these calls and time until the next call; None when unmeasured."""
    totals = {}
    for key in ("tokens", "seconds"):
        values = [row["tool"][key] for row in evidence if key in row.get("tool", {})]
        totals[key] = round(sum(values), 1) if values else None
    return totals


def markdown(findings, total_tokens=None, total_calls=None):
    lines = ["# Diagnosis and recommendations", "", "Local deterministic signals; task correctness remains unknown.", ""]
    ranked = sorted(((row, finding) for finding in findings for row in finding["suggestions"]),
                    key=lambda pair: (-pair[0]["tokens"], -pair[0]["incidents"]))
    if ranked:
        lines.extend(["## Suggested fixes", ""])
        lines.extend(f"- [{row['target']}] {row['change']} ({row['tokens']:,} tokens, {row['incidents']} incidents"
                     + (f" in {row['turns']} long turn{'s' * (row['turns'] != 1)}" if "turns" in row else "")
                     + f"; {finding['rule']}, repository {finding['repository_id'][:12]})"
                     for row, finding in ranked[:SUGGESTION_LINES])
        if len(ranked) > SUGGESTION_LINES:
            lines.append(f"- and {len(ranked) - SUGGESTION_LINES} more (use --format json)")
        lines.append("")
    for finding in findings:
        lines.extend([f"## {finding['issue_id']}: {finding['rule']}", "",
                      finding["description"], "", finding["recommendation"], "",
                      f"Repository: {finding['repository_id'][:12]}. "
                      f"Incidents: {finding['incidents']}; independent provider-scoped sessions: {finding['sessions']}. "
                      f"Classification: {finding['classification']}. Draft eligible: {finding['eligible_for_draft']}.", ""])
        tokens, seconds = finding["cost"]["tokens"], finding["cost"]["seconds"]
        if tokens is not None or seconds is not None:
            share = f" ({tokens / total_tokens:.1%} of scanned)" if tokens and total_tokens else ""
            # Rates and shares, not totals, compare windows of different length.
            rate = f"; {finding['incidents'] * 1000 / total_calls:.1f} incidents per 1k tool calls" if total_calls else ""
            lines.extend([f"Cost: {tokens or 0:,} tokens{share}; {(seconds or 0) / 60:.1f} min{rate}.", ""])
        lines.append("Evidence:")
        evidence = finding["evidence"]
        lines.extend(f"- {row['provider']}/{row['session_id']}/{row['event_id']}" for row in evidence[:EVIDENCE_LINES])
        if len(evidence) > EVIDENCE_LINES:
            lines.append(f"- and {len(evidence) - EVIDENCE_LINES} more (use --format json)")
        lines.extend(["", *finding["limitations"], ""])
    if not findings:
        lines.append("No supported signals found. Missing telemetry is not proof of success.")
    return "\n".join(lines) + "\n"
