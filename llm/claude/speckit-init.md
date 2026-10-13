---
description: Set up Spec Kit in this project on demand
---

Set up Spec Kit in the current Git repository:

1. If `git status --short` shows changes, stop and ask the user to commit or stash them.
2. If `.specify/` is missing, run `specify init --here --force --non-interactive --integration claude`; otherwise, if `specify integration status` does not list claude, run `specify integration install claude`.
3. Summarize the new and changed paths from `git status --short`; do not commit them.
4. Tell the user to restart Claude Code if the `speckit-*` skills are not listed yet, run `/speckit-constitution` once if `.specify/memory/constitution.md` is still the template, then run `/speckit-specify <feature>`.
