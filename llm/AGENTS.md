# Project Instructions

Use this file as the default operating policy for coding tasks in this repository.

## Priorities

1. Understand the real code path before editing.
2. Prefer the smallest correct change.
3. Retrieve only the code/context needed.
4. Preserve correctness, security, validation, accessibility, and data integrity.
5. Validate the change with the narrowest useful checks.

## Ponytail: build less

For every implementation, stop at the first rung that works:

1. Does this need to be built at all?
2. Does it already exist in this codebase? Reuse it.
3. Does the standard library solve it?
4. Does the native platform solve it?
5. Does an already-installed dependency solve it?
6. Can the correct solution be one line?
7. Otherwise write the minimum new code that works.

Do not add speculative abstractions, dependencies, configuration, scaffolding, or extra files.

For bugs, fix the shared root cause rather than only the reported symptom. Check callers/references before changing shared behavior.

Minimalism must never remove trust-boundary validation, security controls, data-loss prevention, accessibility, or explicit requirements.

If Ponytail skills are available, use the normal/full policy for coding tasks and prefer `@ponytail-review` before finalizing a non-trivial diff.

## Serena: semantic code navigation first

When Serena is available and the task concerns normal source code:

1. Ensure the current repository is the active Serena project.
2. Prefer symbol-level retrieval over broad grep/full-file reads.
3. Start with structure, then narrow:
   - `get_symbols_overview`
   - `find_symbol`
   - `find_referencing_symbols`
4. Request symbol bodies only when they are needed.
5. Before changing shared code, inspect relevant callers/references.
6. Use Serena symbol-level edits/refactors when they are safer and more precise than text editing.

Use built-in filesystem/search tools instead when Serena is a poor fit: non-code files, generated content, exact text search, unsupported languages, or tiny known files.

Do not read entire files merely to locate one known symbol.

## Context7: external library/API knowledge

Use Context7 only when implementation depends on third-party library/API behavior, especially when the API is version-sensitive, fast-moving, unfamiliar, or recently changed.

Decision rule:

```text
Question about this repository?
    → Serena

Question about an external dependency/API?
    → Context7

Stable language/runtime behavior already known?
    → use neither
```

Examples:

```text
"Where is our FastAPI app created?" → Serena
"How does FastAPI StreamingResponse work in this version?" → Context7
```

When using Context7:

1. Query only the dependency/API relevant to the task.
2. Prefer the project-installed dependency/version when known.
3. Retrieve only the documentation needed for the implementation decision.
4. Apply the result to the existing project pattern rather than introducing a new abstraction.
5. Do not query Context7 reflexively on every task.

Context7 should complement Serena, not replace it: Serena explains our code; Context7 explains external code/APIs.

## RTK: compact shell output

- In Codex, prefix supported shell commands with `rtk`; follow the imported `RTK.md`.
- In Claude Code, rely on the installed command hook.
- Prefer narrow commands and tests even with RTK enabled.
- If exact unfiltered output is required, bypass RTK for that command:

```bash
RTK_DISABLED=1 <command>
```

- Never depend on RTK filtering for correctness; rerun raw output when details are missing.

## Headroom: context transport

Treat Headroom as transparent infrastructure.

- Continue minimizing reads, logs, and tool output before they reach Headroom.
- Do not generate broad output because Headroom may compress it.
- Never depend on compressed context for correctness.
- If a required detail appears to have been compressed away, use Headroom retrieval when available or rerun the smallest relevant raw read/command.
- Do not start/configure another Serena instance from the agent unless explicitly asked; Serena ownership is a host/bootstrap concern.

## Default workflow

For a code change:

1. Understand the task and identify the likely code path.
2. Use Serena to locate the relevant symbols and references.
3. Read only the bodies needed to make the decision.
4. If the change depends on a third-party library/API, query Context7 narrowly for the relevant behavior/version.
5. Apply the Ponytail ladder and choose the smallest correct design.
6. Edit the fewest files necessary.
7. Run the narrowest relevant test/lint/type/build checks.
8. Let RTK compact supported shell output.
9. Inspect the final diff for accidental scope growth.
10. Use `@ponytail-review` when available for non-trivial diffs.
11. Report what changed, validation performed, and any material limitation.

## Context discipline

Avoid:

- full repository dumps;
- broad recursive grep when a semantic symbol query will work;
- whole-file reads when one symbol is sufficient;
- repeated retrieval of the same content;
- Context7 lookups unrelated to a concrete dependency/API question;
- huge raw test/build logs;
- speculative exploration unrelated to the requested change.

Prefer:

```text
overview → target symbol → references → required body → edit → narrow validation
```

## Graceful degradation

Optimization tools must never block the task.

If Serena, Context7, RTK, Ponytail, or Headroom is unavailable or malfunctioning, continue with Codex's built-in capabilities while preserving the same principles: understand first, retrieve narrowly, make the smallest correct change, and validate it.
