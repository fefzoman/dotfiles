# Agent Policy

Make the smallest complete change after tracing the code path and callers. Reuse existing code, stdlib, or installed tools; add no speculative features or dependencies. Preserve correctness, security, trust-boundary validation, data-loss prevention, accessibility, error handling, and explicit requirements.

## Coding

- Ponytail supplies coding guidance; do not duplicate its full rules here.
- Reuse active Ponytail policy and skill instructions already supplied in this conversation; load additional procedures only for a named skill or a non-trivial task that needs them. Small config and dependency setup tasks need no general workflow skill.
- Comments explain only a constraint the code cannot show, in one line (two at most). Fix violating comments in touched lines.
- Before committing changes to more than about 30 lines of code, use @ponytail-review; config and generated files are excluded.

## Retrieval

- Use Serena only when symbol or reference lookup helps. Read its manual once, then activate with the returned session ID before symbol calls; never start another server unless asked. Small config-only tasks use file tools.
- Code by behavior, or part of a large file (SQL, Terraform, YAML, docs too): run `smart-read search "<question>" --lexical [--path P]` inside the target Git repository, or `smart-read outline FILE`; read only the returned line ranges. `--path` filters results, not repository discovery.
- Embedding indexing: run `smart-read index` only when the user explicitly requests it, inside the target repository, in the foreground. Never detach it (`&`, `nohup`) or leave its tool session unmonitored; poll until it exits and stop it on cancellation. Search never creates embeddings; omit `--lexical` only when semantic retrieval is needed.
- Non-code, generated content, unsupported languages, exact-text searches, and small known files: plain file tools. Reuse reads and tool discovery after an interruption; repeat only failed or incomplete operations.
- External API/library behavior that is unfamiliar or version-sensitive: Context7, at the version pinned in the project environment or lockfile. Stable language behavior needs neither tool.
- For disputed facts, uncertain compatibility or repeated failures needing a new hypothesis, use the investigation skill. Distinguish an upgrade target from installed versions and verify the returned source version.

## Delivery

- Apply relevant skills within these rules; load only the current step's context.
- Use natural-article for substantive documentation or articles; a short setup note needs no extra writing procedure.
- Run Superpowers brainstorming, writing-plans, worktrees, and subagent orchestration only when the user asks; keep designs and plans to a short inline outline, with no document file unless asked.
- Keep tools, plugins, skills, model and effort stable within a session. Apply configuration updates before starting a new session. Superpowers is opt-in; enable it before a new session when requested.
- Priority: explicit user requirements → agent policy → Superpowers defaults.

## Tools

- Use RTK for supported noisy commands when compact output suffices. Use automatic rewriting only with a verified active hook; otherwise prefix manually. Keep exact-output and unsupported commands native.
- Keep searches and logs narrow; use rg's own count, sorting, and exclusion flags instead of pipelines that bypass RTK. Prefer pgrep, diff stats before targeted diffs, and bounded failure logs.
- Recover details RTK hid with RTK_DISABLED=1; verify recovered source before relying on it.
- Discover tool names first; retrieve only needed schemas. Project shell results to status and relevant output, and equivalent MCP results to one representation; preserve distinct content, errors, warnings and resource links. For MCP, emit `content` and `isError`, not the equivalent `structuredContent` too. For shell results, emit only exit status, session ID and relevant output. Save large logs locally, return bounded diagnostics and a recovery path; do not summarize them with another model.
- For running commands, retain the process/session ID and use native waits. Wait about 30 seconds for ongoing work, increasing to 60 seconds when progress is unchanged; report changed progress, completion or failure. Preserve cancellation and final exit status; avoid separate sleeps and repeated log tails.
- Never suggest /model or a reasoning-effort change mid-session: each rewrites the cached context. Delegate work that needs another model or effort to `codex exec -m <model> -c model_reasoning_effort=<level>`.

## Finish

Run the narrowest meaningful validation and review the final diff for scope and unnecessary comments. Commit regularly using the repo's prefix convention and a concise message; never add AI attribution to code, commits, or PRs. Report what changed, validation, and material limitations. If a tool is unavailable, continue with built-in tools under the same rules.
