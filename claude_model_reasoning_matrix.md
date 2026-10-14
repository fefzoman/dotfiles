# Claude model switching guide

Use **Opus 5.5 / Medium** as the default, if available. Switch only when the current setting is a poor fit or the work stalls.

| Signal | Switch to | Why |
|---|---|---|
| Rename, formatting, boilerplate, or another small bounded edit | Haiku 5.5 / Low | Save the stronger setting for work that needs it. |
| Routine implementation, tests, or debugging | Opus 5.5 / Medium | Default balance for everyday development. |
| The task spans several files, needs careful investigation, or Medium misses the cause | Opus 5.5 / High | Give the same model more reasoning for harder work. |
| High still cannot resolve an architectural choice, uncertain root cause, security-sensitive change, or long multi-stage problem | Opus 5.5 / XHigh | Deeper reasoning for the hardest problems. |
| XHigh still stalls on critical work where correctness outweighs cost | Opus 5.5 / Max | Highest setting. |
| The difficult part is resolved and remaining work is routine | Opus 5.5 / Medium | Step back down for follow-up work. |
| Remaining work is only a tiny edit | Haiku 5.5 / Low | Use the lighter setting for trivial follow-up. |

## Switching loop

1. Start with the default or the row that matches the task.
2. If progress stalls, increase effort on Opus first; lower effort on Opus 5.5 often matches older models at higher effort.
3. If XHigh still stalls, move to Max. This is the cap; reassess the problem or gather more evidence if it still stalls.
4. Once the hard part is done, switch back to Opus / Medium for routine follow-up. Use Haiku / Low only when the remaining work is a tiny edit. Keep the current setting if progress is steady.

Examples: a clear feature request → **Opus / Medium**; repeated unsuccessful debugging → **Opus / High**, then **Opus / XHigh** if needed; simple cleanup → **Haiku / Low**; search-heavy subagents → **Haiku or Sonnet / Low**.

Choose only models and effort levels available in your Claude Code version and plan. Set a starting default in `~/.claude/settings.json`:

```json
{
  "model": "opus",
  "effortLevel": "medium"
}
```

Switch per session with `/model` and `/effort`; subagents can set their own `model` and `effort`. Use `/usage` to inspect plan usage. Judge cost per completed task, not per request: a stronger setting solving a task in one pass may be cheaper than repeated attempts with a lighter one. These recommendations are practical heuristics, not official benchmarks or fixed usage multipliers.
