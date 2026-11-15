"""Conservative session snapshots; completion is never proof of correctness."""


def summarize(events):
    sessions = {}
    for event in events:
        key = (event["provider"], event["repository_id"], event["session_id"])
        if key not in sessions:
            sessions[key] = {
                "provider": key[0], "repository_id": key[1], "session_id": key[2],
                "coverage": "metadata_only", "status": "incomplete", "outcome": "unknown",
                "collection_mode": "hooks", "ordering_uncertain": True,
                "command_outputs_available": False, "final_validation": "unavailable",
                "cost_usage": "unavailable", "missing_event_count": None,
                "events": 0, "gaps": 0, "tool_failures": 0, "turn_completions": 0,
                "identified_turns": set(), "open_tools": set(), "started": False, "ended": False,
            }
        row = sessions[key]
        row["events"] += 1
        kind = event["event_type"]
        if kind != "session.ended":
            row["ended"] = False
        if kind == "session.started":
            row["started"], row["ended"] = True, False
        elif kind == "session.ended":
            row["ended"] = True
        elif kind == "collector.gap":
            row["gaps"] += 1
        elif kind == "turn.completed":
            row["turn_completions"] += 1
        if event.get("turn_id"):
            row["identified_turns"].add(event["turn_id"])
        if kind == "tool.started":
            row["open_tools"].add(event.get("span_id", event["event_id"]))
        elif kind in ("tool.completed", "tool.failed"):
            row["open_tools"].discard(event.get("span_id"))
            if kind == "tool.failed" or event.get("tool", {}).get("outcome") == "failure":
                row["tool_failures"] += 1
    result = []
    for row in sessions.values():
        row["identified_turns"] = len(row["identified_turns"])
        row["unclosed_tools"] = len(row.pop("open_tools"))
        started, ended = row.pop("started"), row.pop("ended")
        if started and ended and not row["gaps"] and not row["unclosed_tools"]:
            row["status"] = "ended"
        result.append(row)
    return result


def markdown(rows):
    lines = ["# Agent feedback report", "",
             "Metadata-only coverage; unknown outcome is not a failed task. "
             "Missing events cannot be counted, clocks are uncertain, command output and final "
             "validation are unavailable, and no usage/cost is inferred.", "",
             "| Provider | Repository | Session | Status | Events | Tool failures | Known gaps |",
             "| --- | --- | --- | --- | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row['provider']} | {row['repository_id'][:12]} | {row['session_id'][:12]} "
                     f"| {row['status']} | {row['events']} | {row['tool_failures']} | {row['gaps']} |")
    if not rows:
        lines.extend(["", "No events in the retained window. This does not establish hook health."])
    return "\n".join(lines) + "\n"
