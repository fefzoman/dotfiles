---
name: speckit-init
description: Set up Spec Kit in the current project. Use only when the user asks for speckit-init or to set up Spec Kit.
---

Set up Spec Kit in the current Git repository:

1. If `git status --short` shows changes, stop and ask the user to commit or stash them.
2. If `.specify/` is missing, run `specify init --here --force --non-interactive --integration codex --integration-options="--skills"`; otherwise, if `specify integration status` does not list codex, run `specify integration install codex --integration-options="--skills"`.
3. Summarize the new and changed paths from `git status --short`; do not commit them.
4. Tell the user to restart Codex if the `speckit-*` skills are not listed yet, run `$speckit-constitution` once if `.specify/memory/constitution.md` is still the template, then run `$speckit-specify <feature>`.
