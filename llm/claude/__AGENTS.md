# Agent Policy

Understand the real code path before editing, make the smallest correct change, retrieve only the context needed, and validate with the narrowest useful check. Never trade away correctness, security, trust-boundary validation, data-loss prevention, accessibility, or explicit requirements.

## Build less (Ponytail)

- Stop at the first rung that works: not needed → already in the codebase → stdlib → native platform → installed dependency → one line → minimum new code.
- No speculative abstractions, dependencies, configuration, scaffolding, or extra files.
- Bugs: fix the shared root cause; check callers before changing shared behavior.
- Comments: default to none. Add one only for what the code can't say (a non-obvious constraint, workaround, or invariant), in one line, two at most. Never restate the code, explain its mechanics, point elsewhere, or mention history, edits, or requesters; those belong in the commit message. Fix violating comments in lines you touch.
- Before committing, run the ponytail:ponytail-review skill when the diff adds or changes more than about 30 lines of code (not config or generated files).

## Retrieval

- This repository's code → Serena. External library/API behavior (version-sensitive, unfamiliar, fast-moving) → Context7. Stable, known language behavior → neither.
- Serena: overview → symbol → references → only the bodies needed. In a multi-repo workspace, call `activate_project` with the repo's path before symbol calls and again when moving to another repo; otherwise don't re-activate. Never read a whole file to find one known symbol. Prefer symbol-level edits when they are more precise.
- Use plain file/search tools for non-code files, generated content, exact-text search, unsupported languages, or tiny known files.
- Context7: query only the dependency in question, at the version the project's environment pins (`.venv`, `uv.lock`, `poetry.lock`, `requirements*.txt`, `node_modules`), named in `libraryId` or the query; apply the answer to the existing pattern.
- Don't re-read the same content or re-discover tools already known.

## Structured delivery (Spec Kit + Superpowers)

- For a feature managed by Spec Kit, its active specification, plan, and tasks are the persistent source of truth for scope and implementation state.
- Do not create a parallel Superpowers design or implementation plan for the same Spec Kit feature. Skip equivalent `brainstorming` / `writing-plans` stages unless explicitly requested or no Spec Kit artifacts exist.
- During implementation, use applicable Superpowers disciplines within the existing Ponytail, retrieval, validation, and review rules; do not duplicate Spec Kit artifacts or start another Serena server.
- If implementation discoveries change requirements, design, or remaining work, reconcile the relevant Spec Kit artifact instead of creating a second planning document.
- Load only the active feature artifacts and the skills needed for the current step; do not read the whole specs tree or skill library.
- Small, local changes do not require the Spec Kit lifecycle unless explicitly requested or the repository requires it.
- Resolve conflicts in this order: explicit user requirements, applicable agent policy, project constitution, active specification, plan, tasks, then Superpowers defaults.

## Shell output (RTK) and transport (Headroom)

- Use RTK for supported noisy commands whenever compacted output is sufficient.
- Never assume RTK command rewriting is active merely because `RTK.md` or `rtk init` is present.
- Use the automatic rewrite hook when it is installed and active.
- Do not wrap unsupported commands or commands where exact output is required. In particular, do not invent pass-through forms such as `rtk sed`; run the native command instead.
- Keep commands narrow: `pgrep` over `ps`, `git diff --stat` before targeted diffs, bounded failure tails instead of full build logs.
- RTK skips `find`/`rg`/`grep`/`ls` whose output feeds `sort`, `wc`, `xargs`, `awk`, another `rg`/`grep`, or `$()`. Use the tool's own flags instead: `rg --files --sort path` to list, `rg -c` to count matches, `--glob '!path'` to exclude files, `wc -l <paths or glob>` for line counts.
- Headroom compresses traffic transparently. Don't produce broad output because it will be compressed, and never rely on compressed content for correctness.
- If filtering or compression hid a needed detail, rerun only that command with `RTK_DISABLED=1` or use Headroom retrieval.
- Never start or configure another Serena instance unless asked.

## Git

- Commit regularly.
- Commit messages are one line with a short body description, following the repo's prefix convention if it has one.
- Never add `Co-Authored-By` trailers, "Generated with" lines, or any other AI attribution to commits, PRs, or code.

## Finish

Check the final diff for scope growth and reread every added comment: delete it if the code already says it, otherwise cut it to one line. Then report what changed, how it was validated, and any material limitation. If any of these tools is unavailable, continue with built-in tools under the same principles.
