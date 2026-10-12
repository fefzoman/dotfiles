#!/usr/bin/env python3
"""Adapt RTK's Claude command rewriter to Codex's hook output contract."""

import json
import subprocess
import sys


def main() -> None:
    payload = sys.stdin.read()
    result = subprocess.run(
        ["rtk", "hook", "claude"], input=payload, text=True,
        capture_output=True, check=True, timeout=4,
    )
    if not result.stdout.strip():
        return
    output = json.loads(result.stdout)
    hook = output.get("hookSpecificOutput", {})
    if "updatedInput" in hook:
        hook["permissionDecision"] = "allow"
    print(json.dumps(output))


if __name__ == "__main__":
    main()
