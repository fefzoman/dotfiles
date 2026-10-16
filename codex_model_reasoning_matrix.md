# Codex model switching guide

Use **GPT-6.1 Sol / Medium** as the default, if available. Switch only when the current setting is a poor fit or the work stalls.

| Signal | Switch to | Thinking tokens/call | Why |
|---|---|---:|---|
| Rename, formatting, boilerplate, or another small bounded edit | GPT-6 Luna / Low | No local sample | Save the stronger setting for work that needs it. |
| Routine implementation, tests, or debugging | GPT-6.1 Sol / Medium | 17 | Default balance for everyday development. |
| The task spans several files, needs careful investigation, or Medium misses the cause | GPT-6.1 Sol / High | 245 | Give the same model more reasoning for harder work. |
| High still cannot resolve an architectural choice, uncertain root cause, or critical multi-stage problem | GPT-6 Astra / High | 113 | Highest recommended setting. |
| The difficult part is resolved and remaining work is routine | GPT-6.1 Sol / Medium | 17 | Step back down for follow-up work. |
| Remaining work is only a tiny edit | GPT-6 Luna / Low | No local sample | Use the lighter setting for trivial follow-up. |

Thinking tokens/call is the mean recorded `reasoning_output_tokens` per API call, including calls with zero reasoning tokens, rounded to the nearest integer. Samples: Sol / Medium **209 calls**; Sol / High **2,547 calls**; Astra / High **581 calls**. Luna / Low has no recorded calls; Luna / Medium averaged **51** over **20 calls**, which is a different setting.

Measured across `sessions` and `archived_sessions` in both `~/.codex` and `~/.codex-work`, including subagents and automatic reviews, through **2026-10-16 04:46 UTC**: **314 files**, **26,649 calls with model context**, spanning 2026-01-07 to 2026-10-16. Per-response usage records take precedence over legacy token-count events; repeated cumulative events and copied history are deduplicated. Excluded 432 usage entries without model context and 40 synthetic context-size snapshots with zero input and output tokens.

These are workload-dependent observations, not controlled comparisons or total-cost estimates; Astra's lower observed mean does not establish that it is cheaper than Sol.

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
