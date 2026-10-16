# Claude model matrix benchmark

This compares Claude settings on the same coding tasks in this repository: 8 routine tasks × 3 repeats × 6 settings, plus 4 harder tasks × 3 repeats × 3 settings, for 180 trials. Every trial starts from an independent copy of dotfiles at `270076e`. Results apply to these bounded Python and shell maintenance tasks, not arbitrary repositories or large architectural work.

The routine suite runs `claude-haiku-5-5` / Low and Medium, and `claude-opus-5-5` / Medium, High, XHigh and Max. The harder suite runs Haiku / Low, Opus / High and Opus / XHigh. The tasks cover:

| Task | Suite | Required behavior |
|---|---|---|
| `pipe` | routine | Fix an injected bug: piped `cat FILE \| head` must not get the large-read hint. |
| `min_lines` | routine | `READ_HINT_MIN_LINES=0` disables the hint; the 80-line default and custom thresholds still work. |
| `pyproject` | routine | Read `==` pins, extras included, from `[project].dependencies` in the Context7 guard. |
| `mentions` | routine | Fix an injected bug: version `2.4.1` must not match a query naming `12.4`. |
| `rename` | routine | Rename the `effort` command to `claude_effort` / `claude-effort` across code, installer and tests. |
| `thinking` | routine | Fix an injected bug: token-profiler must read Claude `thinking_tokens`. |
| `rtk` | routine | The Codex RTK hook exits 0 silently when `rtk` is missing, fails or hangs. |
| `codex_effort` | routine | Fix an injected bug: `codex-effort` must change only the top-level key, not profile tables. |
| `top_model` | harder | Add `token-profiler top --by model [--json]` for Claude and Codex sessions, with per-call metrics. |
| `monorepo` | harder | Fix two injected bugs from one symptom: the guard lost both the git-root lookup and case-insensitive names. |
| `sed_range` | harder | Treat `sed -n 'A,Bp' FILE` as a ranged read, with `$`, small-range and pipe cases. |
| `effort_arg` | harder | Optional, validated effort level for both effort commands; bad values exit 2 and leave the file untouched. |

The full prompts and external acceptance checks are in [tasks.py](tasks.py). Every check fails on its start state, and each bug-injection check passes on the unmodified commit (`run.py --validate`). Each trial must pass its acceptance check and the existing tests of the touched area, within 30 minutes. A model's claim of success does not affect grading. Failed trials remain in usage and cost totals.

All trials use Claude Code 2.1.301 headless (`claude -p`), the personal profile with its global instructions, hooks and plugins, a fresh session, and `acceptEdits` with Read, Grep, Glob, Edit, Write and Bash allowed. MCP servers, subagents and web tools are disabled. Up to six trials run concurrently in shuffled order. Backend caches are not flushed or forced cold. 24 harder trials hit the account's spend limit before doing any work; they were discarded and rerun after the limit reset.

## Metrics

Counters come from each trial's final `modelUsage` entry for the requested model; API calls are distinct assistant message IDs in the stream.

- **Fresh input/call:** input not read from cache (uncached input plus cache writes), divided by model API calls.
- **Reasoning/call:** `thinkingTokens` divided by model API calls; zero-reasoning calls count.
- **Cache hit:** cache reads divided by total input; this is weighted by input volume.
- **Total cost:** Claude Code's `total_cost_usd`, at API list prices, for all trials including failures. This is not the plan's subscription usage.
- **Success:** trials passing the acceptance check, existing tests and timeout, divided by trials.

## Run and inspect

```bash
python3 benchmarks/claude_matrix/run.py --validate
python3 benchmarks/claude_matrix/run.py
python3 benchmarks/claude_matrix/run.py --regrade
```

The second command uses plan or API usage. Completed trials are reused on restart; trials that ended in an agent error, such as a spend limit, are rerun. Workspaces, event streams and per-trial results are kept in `~/claude-matrix-runs-20261016/`. Aggregates and per-trial counters are written to `results.json` here.

## Results

All 180 saved workspaces were regraded with the final checks. There were no timeouts or agent errors among them.

Routine suite, 24 trials per setting:

| Setting | API calls | Fresh input/call | Reasoning/call | Cache hit | Total API-equivalent cost | Success | Median time |
|---|---:|---:|---:|---:|---:|---:|---:|
| Haiku / Low | 155 | 2,830 | 160 | 89.6% | $0.16 | 24/24 | 20s |
| Haiku / Medium | 169 | 2,820 | 214 | 89.9% | $0.18 | 24/24 | 22s |
| Opus / Medium | 152 | 2,273 | 44 | 90.5% | $4.17 | 24/24 | 28s |
| Opus / High | 165 | 2,177 | 62 | 91.0% | $4.46 | 24/24 | 31s |
| Opus / XHigh | 198 | 2,551 | 195 | 91.1% | $6.64 | 24/24 | 47s |
| Opus / Max | 394 | 2,980 | 966 | 93.6% | $21.51 | 24/24 | 212s |

Harder suite, 12 trials per setting:

| Setting | API calls | Fresh input/call | Reasoning/call | Cache hit | Total API-equivalent cost | Success | Median time |
|---|---:|---:|---:|---:|---:|---:|---:|
| Haiku / Low | 144 | 2,526 | 278 | 93.4% | $0.17 | 11/12 | 32s |
| Opus / High | 130 | 3,037 | 127 | 92.5% | $5.34 | 12/12 | 56s |
| Opus / XHigh | 152 | 3,051 | 318 | 93.0% | $6.93 | 12/12 | 91s |

| Task | Haiku / Low | Opus / High | Opus / XHigh |
|---|---:|---:|---:|
| top_model | 3/3 | 3/3 | 3/3 |
| monorepo | 2/3 | 3/3 | 3/3 |
| sed_range | 3/3 | 3/3 | 3/3 |
| effort_arg | 3/3 | 3/3 | 3/3 |

Every routine trial passed. The one failure, Haiku / Low on its third `monorepo` attempt, restored the git-root lookup but not the case-insensitive name match, so `Flask_Login` still went unchecked.

**Opus / High had the lowest total cost among settings passing every trial in both suites.** Haiku / Low passed every routine trial at about 1/28 of that cost. XHigh matched High at 1.3–1.5× the cost and 1.5–1.6× the time, and Max matched it at 4.8× the cost and 7× the time. The suites do not measure large features, architectural decisions or security audits. Three repeats per task are too few to infer general reliability, and caching is observed rather than forced cold.

[Full per-trial counters and outcomes](results.json). Raw event streams, workspaces and grading output remain in `~/claude-matrix-runs-20261016/`.
