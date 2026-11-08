# Code retrieval benchmark: skill, Serena, and Context7

Latest: the [tool-specific tests and removal decision](SPECIFIC.md) compare
ag/ack against rg and exercise ast-grep on actual structural queries. The
[shell-first dispatcher comparison](SHELL.md) records the preceding candidate's
negative repair-benchmark result. These experiments are not pooled together.

The [CLI-only follow-up](CLI.md) compares plain shell, the previous skill, the
refactored dispatcher, and Context7 CLI in 24 clean trials, with no retrieval MCP
tools exposed. An [earlier contaminated attempt](CLI-BLOCKED.md) is archived
separately and excluded from that comparison.

For the follow-up on full CPython checkouts, with **Serena and Context7 without
the retrieval skill**, see [the large-repository benchmark](LARGE.md). Its arms
and workloads differ; the two experiments are reported separately.

On 2026-11-08, twelve native-agent code-fix trials completed: four distinct tasks,
three retrieval strategies, and up to three workers in parallel. All twelve fixes
passed the same parent-run Python 3.14.7 checks, with no changes to their tests.
These are actual model usage counters, not counts of retrieved text.

| Retrieval strategy | Trials passing | Model calls | Input + output tokens | Cached input | Uncached input |
|---|---:|---:|---:|---:|---:|
| Skill-guided shell retrieval | 4/4 | 27 | 405,110 | 357,248 | 44,322 |
| Skill + Serena retrieval | 4/4 | 37 | 641,294 | 564,096 | 71,646 |
| Skill + Context7 verification | 4/4 | 31 | 542,393 | 481,792 | 55,895 |

Skill-guided shell retrieval consumed **36.8% fewer total tokens than Serena** and
**25.3% fewer than Context7** in this sample. Conversely, Serena added 58.3% and
Context7 added 33.9% relative to the skill baseline. This does not establish that
either tool is generally worse: these were small, self-contained fixes, where
initialization and extra model calls can outweigh retrieval savings.

## Tasks and execution

Each fresh agent read the current retrieval skill, traced `app.py` and its
`test_app.py` callers, implemented a fix in `app.py` only, ran tests, and inspected
the result. All agents used `gpt-6.1-sol` with `medium` reasoning, verified against
every session's recorded context. They inherited the same runtime/tool availability;
the strategy was controlled through the trial prompt, not different tool schemas.

| Code task | Skill | Serena | Context7 |
|---|---:|---:|---:|
| Parse UTF-8 TOML with precise Decimal floats and preserved errors | 109,607 | 171,543 | 116,214 |
| Enforce subprocess timeout, cleanup, and nonzero-exit errors | 85,135 | 136,589 | 125,560 |
| Classify paths without following symlinks or suppressing OS errors | 105,789 | 193,640 | 147,867 |
| Parse boolean CLI flags with intermixed paths and no abbreviations | 104,579 | 139,522 | 152,752 |

There are four distinct code tasks, not twelve distinct questions: every task was
run once per strategy so the totals compare matching workloads. Strategies were
interleaved across waves of different tasks. No documentation-only task is included.
Context7 verified relevant Python 3.14 standard-library APIs before implementation;
Serena retrieved source symbols and references through the existing server. It
automatically expanded/migrated the four local fixture project configurations;
their Python language and read/write settings were preserved.

## Accounting and audit

[code-results.json](code-results.json) contains per-trial totals, per-response usage,
observed MCP calls, model/effort contexts, patches, test results, and session hashes.
[code-manifest.json](code-manifest.json) retains exact prompts, baseline sources,
source/test hashes, workspace paths, and agent identities. Source and tests are
also defined in [code_tasks.py](code_tasks.py).

`collect_code.py` matches native-agent sessions to their parent thread and agent
path, deduplicates response IDs, and sums per-response `token_usage_record` usage.
The sums must match each session's final `thread_token_usage`. Cached input is
already part of input; reasoning is already part of output. Neither is added a
second time. No monetary cost is estimated. Parent preparation, the preflight,
parent grading, and review are outside the measured agent workloads.

All twelve parent grades passed, all test-file hashes matched their baselines,
and the recorded retrieval calls matched their strategy. Three of the four
skill-baseline agents nevertheless called Serena's manual because of a runtime
instruction; three Context7 agents did too. Those costs remain in the totals.
Thus the baseline means **no Serena source retrieval**, not a Serena-free runtime.
The collector's method check deliberately permits manual initialization and checks
call names; it is not a semantic proof that every tool result was used correctly.

Some agent shells resolved `python3` to Python 3.9.6. Their failed attempts and
interpreter discovery remain in their usage; the parent independently ran every
final fix with the same explicit Python 3.14 executable. This adds noise, as do
cache hits, shared infrastructure, scheduling, and one sample per task/strategy.
The tiny fixtures and narrow test contracts do not cover large-repository discovery,
long-lived reuse, other libraries, or complex implementations. In particular, the
path-metadata mock expects `Path.stat(follow_symlinks=False)`, not every semantically
equivalent pathlib implementation. No statistical significance is claimed.

## Checks and reproduction

```sh
python3 -m unittest discover -s benchmarks/retrieval -p 'test_*.py'
python3 benchmarks/retrieval/collect_code.py
```

The first command tests accounting. The second regrades the retained workspaces
and regenerates results from retained native session logs; it needs the recorded
Python executable and local artifacts. To repeat the model experiment, create fresh
workspaces from `code_tasks.py`, restore baseline sources and tests, and launch one
fresh native agent per manifest prompt with the same model/effort. Use at most
three workers, distinct workspace paths, and record the new parent/agent identities
in a new manifest before collection. Do not reuse already-fixed workspaces.

The earlier nested-CLI attempt remains in [results.json](results.json) as blocked
diagnostic evidence, with its legacy runner in `run.py`. Its shell sandbox and MCP
access failed; those failed trials are excluded from every table above. No sandbox
was bypassed, no dependencies were installed, and no production code was changed.
