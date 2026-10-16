# Codex model matrix benchmark

This compares the four settings recommended by the Codex switching guide on the same six coding tasks, twice each: 48 trials, 12 per setting. Every trial starts from an independent local clone of dotfiles at `a5d36f3`. Results apply to these bounded Python maintenance tasks, not arbitrary repositories or large architectural work.

The settings are `gpt-6-luna` / Low, `gpt-6.1-sol` / Medium, `gpt-6.1-sol` / High, and `gpt-6-astra` / High. The six tasks cover:

| Task | Required behavior |
|---|---|
| `line-count` | Count a final line without a newline; preserve empty-file and error handling. |
| `quoted-shell` | Preserve quoted shell control characters while suppressing pipelines and redirections. |
| `codex-hook` | Add Codex command hooks while preserving Claude hooks and rejecting unsupported tools. |
| `version-boundary` | Match exact or major/minor version tokens without substring or wrong-patch matches. |
| `npm-pins` | Add exact package.json dependency pins through the existing validation caller. |
| `tail-boundary` | Preserve complete JSONL records at byte-tail boundaries for both session readers. |

The full prompts are in [run.py](run.py), and external acceptance checks are in [grade.py](grade.py). All six graders fail on the unchanged baseline. Its 21 existing regression tests pass with Python 3.13. Each trial must pass its grader, all 21 regression tests and any tests it adds, finish within 240 seconds, preserve the original tests and commit, and change only its allowed production file or add test files. A model's claim of success does not affect grading. Failed trials remain in usage and cost totals.

All trials use Codex CLI 0.162.1, the personal profile's existing authentication, a fresh conversation, the standard service tier, and workspace-write sandboxing. User config and exec rules are ignored; no custom proxy, hooks or MCP servers are loaded from config. Automatic delegation is disabled. Global instructions and the CLI's built-in prompt remain part of the measured context. Settings rotate through all four launch positions equally; at most two trials run concurrently. Backend caches are not flushed or forced cold. Cache-hit percentage is observed, and sessions do not share conversation history. One preliminary Luna availability call is excluded from trial measurements.

## Metrics

Per-call counters come from each trial's `token_usage_record` records, deduplicated by response ID. Requested model and effort are checked against session context. Summed per-call counters must equal the CLI's final usage totals when the turn completes.

- **Fresh input/call:** sum of `input_tokens - cached_input_tokens`, divided by model API calls.
- **Reasoning/call:** sum of `reasoning_output_tokens`, divided by model API calls; zero-reasoning calls count.
- **Cache hit:** total cached input divided by total input; this is weighted by input volume.
- **Total cost:** API-equivalent USD for all measured attempts, including failures. This is not the account's subscription bill. Reasoning is already included in output and is not billed twice.
- **Task success:** trials passing every acceptance, regression, scope, completion and timeout check, divided by 12.

[Standard API prices](https://developers.openai.com/api/docs/pricing), checked on 2026-10-16, per million tokens for short-context calls:

| Model | Input | Cached input | Cache write | Output |
|---|---:|---:|---:|---:|
| GPT-6 Luna | $0.10 | $0.01 | $0.125 | $0.50 |
| GPT-6.1 Sol | $2.00 | $0.10 | $2.50 | $10.00 |
| GPT-6 Astra | $10.00 | $1.00 | $12.50 | $50.00 |

Cost is `(fresh - cache_write) × input_rate + cached × cached_rate + cache_write × write_rate + output × output_rate`, divided by one million. The runner rejects calls above the short-context boundary instead of pricing them incorrectly.

## Run and inspect

```bash
/opt/homebrew/bin/python3.13 -m unittest discover -s benchmarks/codex_matrix -p test_run.py -q
/opt/homebrew/bin/python3.13 benchmarks/codex_matrix/run.py --prepare
/opt/homebrew/bin/python3.13 benchmarks/codex_matrix/run.py
```

The last command uses account quota. Completed trials are reused on restart. Trial clones, prompts, event logs, grading logs and diffs are retained in `~/codex-matrix-runs-20261016/`. Aggregate results and per-trial counters are written to `results.json` here. Task prompts stay fixed throughout the experiment. Every saved trial workspace is checked against the same final grader before reporting results.

## Results

All 48 saved workspaces were regraded with the same final acceptance checks, original regression tests and added tests. There were no timeouts or usage-accounting mismatches. All 302 model API calls are included, including failed trials.

| Setting | API calls | Fresh input/call | Reasoning/call | Cache hit | Total API-equivalent cost | Success |
|---|---:|---:|---:|---:|---:|---:|
| Luna / Low | 78 | 2,201 | 4.6 | 88.0% | $0.0356 | 9/12 |
| Sol / Medium | 72 | 2,210 | 43.8 | 88.7% | $0.6517 | 12/12 |
| Sol / High | 82 | 2,639 | 103.5 | 87.3% | $0.8805 | 12/12 |
| Astra / High | 70 | 2,299 | 71.9 | 88.2% | $4.1002 | 12/12 |

| Task | Luna / Low | Sol / Medium | Sol / High | Astra / High |
|---|---:|---:|---:|---:|
| line-count | 1/2 | 2/2 | 2/2 | 2/2 |
| quoted-shell | 2/2 | 2/2 | 2/2 | 2/2 |
| codex-hook | 2/2 | 2/2 | 2/2 | 2/2 |
| version-boundary | 2/2 | 2/2 | 2/2 | 2/2 |
| npm-pins | 1/2 | 2/2 | 2/2 | 2/2 |
| tail-boundary | 1/2 | 2/2 | 2/2 | 2/2 |

Luna failures: the first line-count attempt produced an incorrect boolean expression; the second package-pins attempt changed installed-package source precedence; the second JSONL attempt broke unbounded reads. Every other trial passed its acceptance checks and regression tests.

**Sol / Medium had the lowest API-equivalent total cost among settings passing all 12 trials.** The suite does not measure large features, architectural decisions or security audits. Twelve trials per setting are too few to infer general reliability. Caching is observed rather than experimentally forced cold.

[Full per-trial counters and outcomes](results.json). Raw prompts, model event streams, diffs and final grading logs remain in `~/codex-matrix-runs-20261016/`.
