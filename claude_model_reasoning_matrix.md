# Claude Model × Reasoning Effort Matrix

> Practical guidance for Claude Code. Model availability and consumption vary by Claude Code version, plan, and account. Ratings are recommendations, not official benchmarks or fixed usage multipliers.

## 1. Usage matrix

**Legend:** ⭐ Ideal · ✓ Good · △ Situational · — Usually inefficient

| Model | Low | Medium | High | XHigh | Max |
|---|---|---|---|---|---|
| **Haiku 5.5** | ⭐ Small edits, lookups | ✓ Routine coding | △ Bounded debugging | — Complex work | — Complex architecture |
| **Sonnet 5.5** | ⭐ Straightforward implementation | ⭐ Daily development | ⭐ Complex coding | ✓ Difficult investigations | △ Rarely beats Opus / High |
| **Opus 5.5** | ✓ Fast routine work | ⭐ Implementation (model default) | ⭐ Architecture / hard debugging | ⭐ Long agentic, multi-stage work | △ Correctness over cost |
| **Fable 5.1** | △ Expensive for routine work | ✓ Complex implementation | ⭐ Hardest reasoning | ⭐ Critical, long-horizon work | ✓ Exhaustive, uncertain root cause |

## 2. Task-based selection matrix

| Engineering task | Recommended model | Effort |
|---|---|---|
| Rename variables, formatting | Haiku | Low |
| Small, well-defined code change | Haiku / Sonnet | Low / Medium |
| Generate boilerplate or YAML | Haiku | Low |
| Codebase search / Explore subagents | Haiku / Sonnet | Low |
| Write unit tests | Sonnet | Medium |
| Implement a defined feature | Sonnet / Opus | Medium |
| Refactor across multiple files | Opus | Medium / High |
| Investigate failing tests | Opus | High |
| Debug concurrency or race conditions | Opus | High / XHigh |
| Understand an unfamiliar large codebase | Opus | High |
| Design a new system architecture | Opus / Fable | High / XHigh |
| Diagnose complex production failures | Opus / Fable | XHigh |
| Large-scale migration | Opus | XHigh |
| Review security-sensitive changes | Fable | XHigh / Max |
| Autonomous multi-stage implementation | Opus / Fable | XHigh |
| Exhaustive investigation with uncertain root cause | Fable | Max |

**Suggested default:** Opus + Medium (or High) for routine Python, AWS, infrastructure, and data-engineering work; escalate selectively. Lower effort on Opus 5.5 often matches older models at higher effort, so try that before switching models.

## 3. Usage consumption matrix

Qualitative estimates only, **not** measured benchmarks. API list price per 1M tokens (input / output): Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20, Fable 5.1 $10 / $50.

| Model | Low | Medium | High | XHigh | Max |
|---|---|---|---|---|---|
| Haiku 5.5 | Very low | Very low | Low | Low | Variable |
| Sonnet 5.5 | Low | Low–medium | Medium | Medium–high | High |
| Opus 5.5 | Medium | Medium | Medium–high | High | Very high |
| Fable 5.1 | High | High | Very high | Very high | Very high |

Higher effort increases thinking tokens and tool calls, but total usage also depends on context size, retries, and task duration. A capable model solving a task in one pass may be cheaper overall than repeated attempts with a lighter model. Judge cost per completed task, not per request.

## 4. Recommended Claude Code configuration by workload

| Workload | Default | Escalate to |
|---|---|---|
| Quick fixes | Sonnet / Low | Opus / Medium |
| Everyday development | Opus / Medium | Opus / High |
| New feature development | Opus / High | Opus / XHigh |
| Architecture and planning | Opus / XHigh | Fable / XHigh |
| Debugging difficult failures | Opus / XHigh | Fable / Max |
| Long autonomous execution | Opus / XHigh | Fable / XHigh |

Example `~/.claude/settings.json` (only if the model is available on your plan):

```json
{
  "model": "opus",
  "effortLevel": "high"
}
```

Switch per session with `/model` and `/effort`; subagents can set their own `model` and `effort`. Use `/usage` to inspect plan usage.

**Heuristic workload distribution:** Opus / Medium–High for 70–80% of tasks, Opus / XHigh for difficult implementation and debugging, Haiku or Sonnet / Low for search-heavy subagents, and Fable for work that warrants the additional usage. This is a suggested workflow, not a measured optimum.
