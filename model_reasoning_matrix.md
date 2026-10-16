# Model switching guide

Default to **Medium on the main model**. Switch only when the setting is a poor fit or work stalls.

| Signal | Claude | Codex |
|---|---|---|
| Small bounded edit, tiny follow-up, search-heavy subagent | Haiku 5.5 / Low | GPT-6 Luna / Low |
| Routine implementation, tests, debugging; follow-up after the hard part | **Opus 5.5 / Medium** | **GPT-6.1 Sol / Medium** |
| Several files, careful investigation, or Medium misses the cause | Opus 5.5 / High | GPT-6.1 Sol / High |
| High stalls on architecture, uncertain root cause, security, or long multi-stage work (cap) | Opus 5.5 / XHigh | GPT-6 Astra / High |

**Loop:** start at the matching row → on a stall raise effort on the current model first (Haiku/Luna stalls go to Medium) → past the cap, reassess or gather evidence → once the hard part is done, step back to Medium. Keep the setting while progress is steady; verify light-model results.

## Benchmarks

Measured 2026-10-16, each trial in a fresh session on an independent dotfiles copy. Success = external acceptance checks plus the touched area's existing tests. Cost is API-equivalent across all attempts, failures included; subscription usage was not measured and caches were not forced cold. Per-call means include zero-reasoning calls; cache hit = cached ÷ total input.

**Claude Code 2.1.301** at `270076e`: 8 routine tasks × 3 repeats × 6 settings + 4 harder tasks × 3 × 5 = 204 trials. Per-call columns are from the routine suite.

| Setting | Fresh in/call | Reasoning/call | Cache hit | Routine (24) | Harder (12) |
|---|---:|---:|---:|---:|---:|
| Haiku 5.5 / Low | 2,830 | 160 | 89.6% | $0.16 · 24/24 | $0.17 · 11/12 |
| Haiku 5.5 / Medium | 2,820 | 214 | 89.9% | $0.18 · 24/24 | $0.22 · 10/12 |
| Opus 5.5 / Medium | 2,273 | 44 | 90.5% | $4.17 · 24/24 | $4.24 · 12/12 |
| Opus 5.5 / High | 2,177 | 62 | 91.0% | $4.46 · 24/24 | $5.34 · 12/12 |
| Opus 5.5 / XHigh | 2,551 | 195 | 91.1% | $6.64 · 24/24 | $6.93 · 12/12 |
| Opus 5.5 / Max | 2,980 | 966 | 93.6% | $21.51 · 24/24 | — |

**Codex CLI 0.162.1** at `a5d36f3`: 6 tasks × 2 repeats × 4 settings = 48 trials, with the original 21 regression tests; cost at [standard API prices](https://developers.openai.com/api/docs/pricing).

| Setting | Fresh in/call | Reasoning/call | Cache hit | Cost (12) | Success |
|---|---:|---:|---:|---:|---:|
| GPT-6 Luna / Low | 2,201 | 4.6 | 88.0% | $0.0356 | 9/12 |
| GPT-6.1 Sol / Medium | 2,210 | 43.8 | 88.7% | $0.6517 | 12/12 |
| GPT-6.1 Sol / High | 2,639 | 103.5 | 87.3% | $0.8805 | 12/12 |
| GPT-6 Astra / High | 2,299 | 71.9 | 88.2% | $4.1002 | 12/12 |

**Medium on the main model was the cheapest setting passing every trial on both clients.** Opus / Medium ran 7% below High on routine and 21% below on harder tasks; XHigh cost 1.6× and Max 5.2× (8× the time) for the same result. Haiku / Low cost ~1/26 of Opus / Medium and missed one bug cause once; Haiku / Medium cost more and passed fewer harder trials, so skip it. Luna failed line-count, pin-precedence and JSONL-reading trials once each. These small maintenance suites don't cover large features or architecture; escalation rows remain heuristics. Method and runners: [Claude](benchmarks/claude_matrix/README.md) · [Codex](benchmarks/codex_matrix/README.md); per-trial results: [Claude](benchmarks/claude_matrix/results.json) · [Codex](benchmarks/codex_matrix/results.json).

## Setup

Pick only models and efforts your client version and plan offer.

```json
// ~/.claude/settings.json
{ "model": "opus", "effortLevel": "medium" }
```

```toml
# ~/.codex/config.toml
model = "gpt-6.1-sol"
model_reasoning_effort = "medium"
```

Claude: `/model` and `/effort` switch mid-session but rewrite the prompt cache, so in long sessions run `/checkpoint` and `/clear` first; `/usage` shows plan usage; subagents can set their own `model` and `effort`. Codex: use its model controls; `/status` shows the active model and usage. Controls vary by version.
