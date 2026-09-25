# Agent Policy

Understand the real code path before editing, make the smallest correct change, retrieve only the context needed, and validate with the narrowest useful check. Never trade away correctness, security, trust-boundary validation, data-loss prevention, accessibility, or explicit requirements.

## Build less (Ponytail)

- Stop at the first rung that works: not needed → already in the codebase → stdlib → native platform → installed dependency → one line → minimum new code.
- No speculative abstractions, dependencies, configuration, scaffolding, or extra files.
- Bugs: fix the shared root cause; check callers before changing shared behavior.
- Comments describe only the current code, as briefly as possible: why it is this way, never history or provenance. Don't reference previous versions, edits, or who requested them. When editing code, rewrite or delete nearby comments that break this rule.
- Run `ponytail-review` on non-trivial diffs when available.

## Retrieval

- This repository's code → Serena. External library/API behavior (version-sensitive, unfamiliar, fast-moving) → Context7. Stable, known language behavior → neither.
- Serena: overview → symbol → references → only the bodies needed. Activate the project only if uninitialized or changed. Never read a whole file to find one known symbol. Prefer symbol-level edits when they are more precise.
- Use plain file/search tools for non-code files, generated content, exact-text search, unsupported languages, or tiny known files.
- Context7: query only the dependency in question, at the project's version, and apply the answer to the existing pattern.
- Don't re-read the same content or re-discover tools already known.

## Shell output (RTK) and transport (Headroom)

- Claude Code: the hook rewrites commands. Codex: prefix `rtk` only on commands it compacts (git, tests, builds, grep, ls); never pass-through forms like `rtk sed`. This overrides the generic advice in `RTK.md`.
- Keep commands narrow: `pgrep` over `ps`, `git diff --stat` before targeted diffs, bounded failure tails instead of full build logs.
- Headroom compresses traffic transparently. Don't produce broad output because it will be compressed, and never rely on compressed content for correctness.
- If filtering or compression hid a needed detail, rerun that one command with `RTK_DISABLED=1` or use Headroom retrieval.
- Never start or configure another Serena instance unless asked.

## Finish

Check the final diff for scope growth, then report what changed, how it was validated, and any material limitation. If any of these tools is unavailable, continue with built-in tools under the same principles.
