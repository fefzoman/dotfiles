# Agent Policy

Make the smallest complete change after tracing the code path and callers. Reuse existing code, stdlib, or installed tools; add no speculative features or dependencies. Preserve correctness, security, trust-boundary validation, data-loss prevention, accessibility, error handling, and explicit requirements.

## Coding

- Ponytail supplies coding guidance; do not duplicate its full rules here.
- Comments explain only a constraint the code cannot show, in one line (two at most). Fix violating comments in touched lines.
- Before committing changes to more than about 30 lines of code, use the ponytail:ponytail-review skill; config and generated files are excluded.

## Retrieval

- Code: Serena overview → symbol → references → needed bodies. Activate the repo before symbol calls and when switching repos; never start another Serena server unless asked.
- Code by behavior, or part of a large file (SQL, Terraform, YAML, docs too): `smart-read search "<question>" [--path P]` or `smart-read outline FILE`, then read only the returned line ranges.
- Non-code, generated content, unsupported languages, exact-text searches, and tiny known files: plain file tools. Do not reread known content or rediscover available tools.
- External API/library behavior that is unfamiliar or version-sensitive: Context7, at the version pinned in the project environment or lockfile. Stable language behavior needs neither tool.

## Delivery

- Apply relevant skills within these rules; load only the current step's context.
- Run Superpowers brainstorming, writing-plans, worktrees, and subagent orchestration only when the user asks; keep designs and plans to a short inline outline, with no document file unless asked.
- Priority: explicit user requirements → agent policy → Superpowers defaults.

## Tools

- Use RTK for supported noisy commands when compact output suffices. Use automatic rewriting only with a verified active hook; otherwise prefix manually. Keep exact-output and unsupported commands native.
- Keep searches and logs narrow; use rg's own count, sorting, and exclusion flags instead of pipelines that bypass RTK. Prefer pgrep, diff stats before targeted diffs, and bounded failure logs.
- Recover details RTK hid with RTK_DISABLED=1; verify recovered source before relying on it.
- Never suggest /model, /effort or /fast mid-session: each rewrites the cached context. Delegate work that needs another model or effort to a subagent with that setting.

## Finish

Run the narrowest meaningful validation and review the final diff for scope and unnecessary comments. Commit regularly using the repo's prefix convention and a concise message; never add AI attribution to code, commits, or PRs. Report what changed, validation, and material limitations. If a tool is unavailable, continue with built-in tools under the same rules.
