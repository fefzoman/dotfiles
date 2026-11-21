"""Generate fixed, allowlisted instruction drafts; never execute trace content."""

import difflib
import os
import re
import stat

from .diagnosis import RULES

TARGETS = ("AGENTS.md", "CLAUDE.md")
MAX_INSTRUCTION_BYTES = 64 * 1024


class ProposalError(ValueError):
    pass


def propose(repo, finding):
    if not finding["eligible_for_draft"] or finding["rule"] not in RULES or "instruction" not in RULES[finding["rule"]]:
        raise ProposalError("A draft requires at least three incidents across two independent sessions of a supported rule.")
    issue = finding["issue_id"]
    if not re.fullmatch(r"ISSUE-[0-9a-f]{16}", issue):
        raise ProposalError("Invalid issue ID.")
    marker = f"<!-- agent-feedback:{issue} -->"
    instruction = RULES[finding["rule"]]["instruction"]
    block = f"{marker}\n### Recovery guidance\n\n{instruction}\n"
    patches = []
    for name in TARGETS:
        path = repo / name
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            old, exists = "", False
        else:
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_INSTRUCTION_BYTES:
                    raise ProposalError("Instruction targets must be small regular files, not links.")
                raw = stream.read(MAX_INSTRUCTION_BYTES + 1)
                if len(raw) > MAX_INSTRUCTION_BYTES or b"\x00" in raw:
                    raise ProposalError("Instruction target is too large or not text.")
                old, exists = raw.decode("utf-8"), True
        if marker in old:
            if block not in old:
                raise ProposalError("An existing proposal marker has different content; review it manually.")
            continue
        if instruction in old:
            continue
        new = old + ("\n" if old.endswith("\n") else "\n\n" if old else "") + block
        diff = list(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile=f"a/{name}" if exists else "/dev/null", tofile=f"b/{name}"))
        patch = f"diff --git a/{name} b/{name}\n" + ("" if exists else "new file mode 100644\n")
        for line in diff:
            patch += line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        patches.append(patch)
    return {"issue_id": issue, "status": "draft", "validated": False, "human_review_required": True,
            "targets": list(TARGETS), "evidence": finding["evidence"],
            "limitations": finding["limitations"] + ["Review existing policy for conflicts before applying this draft.",
                                                      "Run isolated baseline/candidate checks before claiming improvement."],
            "patch": "".join(patches)}
