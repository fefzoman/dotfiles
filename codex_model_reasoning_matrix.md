# Codex model switching guide

Use **GPT-6.1 Sol / Medium** as the default, if available. Switch only when the current setting is a poor fit or the work stalls.

| Signal | Switch to | Why |
|---|---|---|
| Rename, formatting, boilerplate, or another small bounded edit | GPT-6 Luna / Low | Save the stronger setting for work that needs it; verify the result. |
| Routine implementation, tests, or debugging | GPT-6.1 Sol / Medium | Default balance for everyday development. |
| The task spans several files, needs careful investigation, or Medium misses the cause | GPT-6.1 Sol / High | Give the same model more reasoning for harder work. |
| High still cannot resolve an architectural choice, uncertain root cause, or critical multi-stage problem | GPT-6 Astra / High | Highest recommended setting. |
| The difficult part is resolved and remaining work is routine | GPT-6.1 Sol / Medium | Step back down for follow-up work. |
| Remaining work is only a tiny edit | GPT-6 Luna / Low | Use the lighter setting for trivial follow-up. |

## Controlled coding benchmark

Measured on 2026-10-16 with Codex CLI 0.162.1: **six identical coding tasks × two repeats × four settings = 48 trials**, each in a fresh session and independent copy of dotfiles at `a5d36f3`. Tasks cover counting, shell parsing, hook compatibility, version validation, package pins and JSONL reading. Success requires passing external acceptance checks, the original 21 regression tests and any added tests, while preserving the allowed scope.

| Setting | Fresh input/call | Reasoning/call | Cache hit | Total API-equivalent cost | Task success |
|---|---:|---:|---:|---:|---:|
| GPT-6 Luna / Low | 2,201 | 4.6 | 88.0% | $0.0356 | 75.0% (9/12) |
| GPT-6.1 Sol / Medium | 2,210 | 43.8 | 88.7% | $0.6517 | 100.0% (12/12) |
| GPT-6.1 Sol / High | 2,639 | 103.5 | 87.3% | $0.8805 | 100.0% (12/12) |
| GPT-6 Astra / High | 2,299 | 71.9 | 88.2% | $4.1002 | 100.0% (12/12) |

Fresh input means input minus cached input. Per-call means include zero-reasoning calls; cache hit is total cached input divided by total input. Each cost covers all 12 attempts, including failures, at [standard API prices](https://developers.openai.com/api/docs/pricing). Reasoning is already included in output pricing. Subscription charges were not measured, and backend caches were not forced cold.

**Sol / Medium was the cheapest setting with 12/12 passes on this suite.** Luna failed one line-count trial, one pin-precedence trial and one JSONL-reading trial. This small maintenance suite does not establish performance on large features or architectural work; the escalation recommendations above remain heuristics. [Full method, task breakdown and reproducible runner](benchmarks/codex_matrix/README.md) · [Per-trial results](benchmarks/codex_matrix/results.json).

## Switching loop

1. Start with the default or the row that matches the task.
2. If progress stalls, increase effort on the current model first.
3. If High still stalls, move to Astra / High. This is the cap; reassess the problem or gather more evidence if it still stalls.
4. Once the hard part is done, switch back to Sol / Medium for routine follow-up. Use Luna / Low only when the remaining work is a tiny edit. Keep the current setting if progress is steady.

Examples: a clear feature request → **Sol / Medium**; repeated unsuccessful debugging → **Sol / High**, then **Astra / High** if needed; simple cleanup → **Luna / Low**.

Choose only models and effort levels available in your Codex installation and account. Set a starting default in `~/.codex/config.toml`:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "medium"
```

Change model or effort in the active Codex session using its model controls; `/status` in Codex CLI shows the active model and available usage information. Exact controls can vary by Codex version. These recommendations are practical heuristics, not official benchmarks or fixed usage multipliers.
