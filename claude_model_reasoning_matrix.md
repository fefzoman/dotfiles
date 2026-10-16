# Claude model switching guide

Use **Opus 5.5 / High** as the default; the installer sets it. Choose the setting when a session starts: a mid-session `/model` or `/effort` switch rewrites the prompt cache, which costs more than the thinking it saves.

| Signal | Start with | Thinking tokens/call | Why |
|---|---|---:|---|
| Rename, formatting, boilerplate, or another small bounded edit | Haiku 5.5 / Low | 152 | Cheapest setting; Medium averaged 436 on the same tasks and was not needed. |
| Routine implementation, tests, debugging, or multi-file investigation | Opus 5.5 / High | 271 | Medium (232) saves only 39 tokens per call, too little to give up reasoning. |
| High cannot resolve an architectural choice, uncertain root cause, security-sensitive change, or long multi-stage problem | Opus 5.5 / XHigh | 564 | 2.1× High, re-read on every later call; reserve for the hardest problems. |
| XHigh still stalls on critical work where correctness outweighs cost | Opus 5.5 / Max | ~2,700 | ~10× High; last resort. |

Thinking tokens/call is the mean per API call across local personal and work transcripts as of 2026-10-16 (Max from only 27 calls; Haiku from a 50-task benchmark of small edits and lookups). Claude keeps thinking in context, so every later call re-reads it.

## Switching loop

1. Start with the row that matches the task: `claude --model haiku --effort low` for a small edit, plain `claude` otherwise.
2. If High stalls, escalate without a mid-session switch: `/checkpoint`, `/clear`, `/effort xhigh`; the fresh chat continues from the checkpoint. For a new chat, use `claude --effort xhigh`.
3. If XHigh stalls, do the same with Max. This is the cap; reassess the problem or gather more evidence if it still stalls.
4. Once the hard part is done, finish in the current session; stepping down mid-session saves less than the cache rewrite costs. The next session starts at the default.

Examples: a clear feature request → **Opus / High**; repeated unsuccessful debugging → **Opus / XHigh** in a fresh chat; simple cleanup → **Haiku / Low**; search-heavy subagents → **Haiku / Low**.

Choose only models and effort levels available in your Claude Code version and plan. The installer writes `effortLevel` to each profile's `settings.json`; set `model` yourself:

```json
{
  "model": "opus",
  "effortLevel": "high"
}
```

Subagents can set their own `model` and `effort` without touching the parent's cache. Use `/usage` to inspect plan usage. Judge cost per completed task, not per request: a stronger setting solving a task in one pass may be cheaper than repeated attempts with a lighter one. These recommendations are practical heuristics, not official benchmarks or fixed usage multipliers.
