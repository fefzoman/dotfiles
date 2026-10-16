# Claude model switching guide

Use **Opus 5.5 / High** as the default, if available. Switch only when the current setting is a poor fit or the work stalls.

| Signal | Switch to | Why |
|---|---|---|
| Rename, formatting, boilerplate, or another small bounded edit | Haiku 5.5 / Low | Save the stronger setting for work that needs it; verify the result. |
| Routine implementation, tests, or debugging | Opus 5.5 / High | Default balance for everyday development. |
| The task spans several files, needs careful investigation, or High misses the cause | Opus 5.5 / XHigh | Give the same model more reasoning for harder work. Highest recommended setting. |
| The difficult part is resolved and remaining work is routine | Opus 5.5 / High | Step back down for follow-up work. |
| Remaining work is only a tiny edit | Haiku 5.5 / Low | Use the lighter setting for trivial follow-up. |

## Controlled coding benchmark

Measured on 2026-10-16 with Claude Code 2.1.301: **8 routine tasks × 3 repeats × 6 settings plus 4 harder tasks × 3 repeats × 3 settings = 180 trials**, each in a fresh session and independent copy of dotfiles at `270076e`. Routine tasks cover hook parsing, version matching, package pins, token parsing and a cross-file rename; harder tasks add a two-cause bug and multi-part features. Success requires passing external acceptance checks and the touched area's existing tests.

| Setting | Fresh input/call | Reasoning/call | Cache hit | Routine cost (24) | Routine success | Harder cost (12) | Harder success |
|---|---:|---:|---:|---:|---:|---:|---:|
| Haiku 5.5 / Low | 2,830 | 160 | 89.6% | $0.16 | 24/24 | $0.17 | 11/12 |
| Haiku 5.5 / Medium | 2,820 | 214 | 89.9% | $0.18 | 24/24 | — | — |
| Opus 5.5 / Medium | 2,273 | 44 | 90.5% | $4.17 | 24/24 | — | — |
| Opus 5.5 / High | 2,177 | 62 | 91.0% | $4.46 | 24/24 | $5.34 | 12/12 |
| Opus 5.5 / XHigh | 2,551 | 195 | 91.1% | $6.64 | 24/24 | $6.93 | 12/12 |
| Opus 5.5 / Max | 2,980 | 966 | 93.6% | $21.51 | 24/24 | — | — |

Per-call columns are from the routine suite. Fresh input is input not read from cache; per-call means include zero-reasoning calls; cache hit is cache reads divided by total input. Each cost covers all attempts, including failures, as Claude Code's API-equivalent `total_cost_usd`. Subscription usage was not measured, and backend caches were not forced cold.

**Opus / High was the cheapest setting with every trial passing in both suites.** Haiku / Low passed every routine trial at about 1/28 of the cost and missed one cause of the two-cause bug once. XHigh matched High at 1.3–1.5× the cost; Max matched it at 4.8× the cost and 7× the time, so it is not recommended. This small maintenance suite does not establish performance on large features or architectural work; the escalation recommendations above remain heuristics. [Full method, task breakdown and reproducible runner](benchmarks/claude_matrix/README.md) · [Per-trial results](benchmarks/claude_matrix/results.json).

## Switching loop

1. Start with the default or the row that matches the task.
2. If progress stalls, increase effort on the current model first.
3. If High still stalls, move to XHigh. This is the cap; reassess the problem or gather more evidence if it still stalls.
4. Once the hard part is done, switch back to Opus / High for routine follow-up. Use Haiku / Low only when the remaining work is a tiny edit. Keep the current setting if progress is steady.

Examples: a clear feature request → **Opus / High**; repeated unsuccessful debugging → **Opus / XHigh**; simple cleanup → **Haiku / Low**; search-heavy subagents → **Haiku / Low**.

Choose only models and effort levels available in your Claude Code version and plan. Set a starting default in `~/.claude/settings.json`:

```json
{
  "model": "opus",
  "effortLevel": "high"
}
```

Change model or effort in the active session with `/model` and `/effort`; a mid-session switch rewrites the prompt cache, so in a long session run `/checkpoint` and `/clear` first. `/usage` shows plan usage. Subagents can set their own `model` and `effort`. These recommendations are practical heuristics, not official benchmarks or fixed usage multipliers.
