"""Evidence-linked rules, not assertions about agent intent or task correctness."""

from collections import defaultdict

from .hooks import fingerprint

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
    groups, attempts = defaultdict(list), defaultdict(list)
    for event in terminal.values():
        tool = event.get("tool", {})
        command = tool.get("command_fingerprint")
        failed = event["event_type"] == "tool.failed" or tool.get("outcome") == "failure"
        missing = tool.get("error_family") == "missing_executable" or (tool.get("name") == "Bash" and tool.get("exit_code") == 127)
        if missing and (failed or tool.get("outcome") == "unknown"):
            groups[(event["repository_id"], "missing_executable", command)].append(event)
        if command:
            session = (event["installation_id"], event["provider"], event["session_id"])
            attempts[(event["repository_id"], session, command)].append(event)
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
            "providers": sorted({row["provider"] for row in evidence}),
            "evidence": [reference(row) for row in evidence],
            "task_outcome": "unknown", "coverage": "metadata_only",
            "eligible_for_draft": "instruction" in spec and len(evidence) >= 3 and len(sessions) >= 2,
            "limitations": ["Signals do not establish an instruction defect or avoidable waste.",
                            "Ordering, policy/environment versions and task intent may be missing.",
                            "No correctness, regression or causal improvement has been established."],
        })
    return findings


def markdown(findings):
    lines = ["# Diagnosis and recommendations", "", "Local deterministic signals; task correctness remains unknown.", ""]
    for finding in findings:
        lines.extend([f"## {finding['issue_id']}: {finding['rule']}", "",
                      finding["description"], "", finding["recommendation"], "",
                      f"Incidents: {finding['incidents']}; independent provider-scoped sessions: {finding['sessions']}. "
                      f"Classification: {finding['classification']}. Draft eligible: {finding['eligible_for_draft']}.", "",
                      "Evidence:"])
        lines.extend(f"- {row['provider']}/{row['session_id']}/{row['event_id']}" for row in finding["evidence"])
        lines.extend(["", *finding["limitations"], ""])
    if not findings:
        lines.append("No supported signals found. Missing telemetry is not proof of success.")
    return "\n".join(lines) + "\n"
