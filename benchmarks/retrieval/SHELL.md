# Shell-first retrieval dispatcher: measured comparison

The candidate dispatcher did **not** improve model efficiency on these repairs.
It consumed **9.9% more tokens** and **7.6% more summed task time** than the
pre-change dispatcher. Plain shell remained lowest in the aggregate. All 18
fixes passed independent grading. The agents used `rg` in every arm and never
selected `ag`, `ack`, `ast-grep` or smart-read, so this run does not demonstrate
a benefit from those additional tools.

The dispatcher now chooses one retrieval route rather than adding another tool
call to every task. It keeps `rg` for exact text, offers installed `ag`/`ack` as
alternatives, and uses `ast-grep` for syntax shapes or noisy multiline matches.
Smart-read remains the behavior-discovery and outline route. Context7 is no
longer required by the skill or future-session policy templates. This change
does not uninstall the existing CLI or change the active session's configuration.

The shell tools do not replace external API evidence. The library reference now
starts with the pinned version and installed source/help, then matching official
documentation if the contract remains unresolved. Caller tracing, complete
bodies, validation, error handling and trust-boundary protections remain required.

## Command performance

A warm-cache check ran each command once to warm up, then nine times against one
CPython pathlib file. Times include subprocess startup and capture, without RTK
filtering. The three text searches returned identical line numbers and contents
after normalizing filename/column formatting.

| Tool | Median wall time | Output bytes |
|---|---:|---:|
| rg | 16.75 ms | 75 |
| ag | 67.77 ms | 77 |
| ack | 45.40 ms | 75 |
| ast-grep, different syntax query | 22.40 ms | 359 |

This small check supports retaining `rg` as the default on this machine; adding
tools is not itself a speed improvement. The AST query finds `self.stat()` calls,
whereas the text query finds `def is_dir`, so their times and output sizes do not
establish an AST-versus-text winner. Raw commands, versions, source hash and
results are in [shell-microbench.json](shell-microbench.json). Shared machine load,
fixed command order, one file and warm caches limit interpretation.

Executable examples were tested with piped stdin. In particular, `ack` needs
`--no-filter` to search files reliably in this environment; `-n` disables its
recursion. The `ag` example uses `--vimgrep` to retain filenames and line numbers.
The integration test also verifies that AST matching ignores comment/string
lookalikes and finds a multiline call.

## Actual model consumption and task time

| Arm | Passing trials | Model calls | Input + output tokens | Summed task time | Median task time |
|---|---:|---:|---:|---:|---:|
| Plain shell, no retrieval skill | 6/6 | 36 | 600,486 | 195.04 s | 34.67 s |
| Pre-change dispatcher | 6/6 | 43 | 690,587 | 232.36 s | 37.63 s |
| Candidate shell-first dispatcher | 6/6 | 47 | 759,156 | 250.08 s | 40.47 s |

Relative to plain shell, the candidate used **26.4% more total tokens** and
**28.2% more summed task time**. Its four additional model calls versus the
pre-change dispatcher are consistent with extra workflow overhead, but this
experiment does not isolate the cause of the difference. Reading more tool
instructions does not guarantee fewer retrieval steps. The candidate was left
unchanged during the experiment; these are measurements of the committed skill,
not an unmeasured rewrite made after seeing the results.

| Arm | Input | Output | Cached input | Uncached input |
|---|---:|---:|---:|---:|
| Plain shell | 595,295 | 5,191 | 525,440 | 69,855 |
| Pre-change dispatcher | 684,990 | 5,597 | 613,248 | 71,742 |
| Candidate dispatcher | 752,731 | 6,425 | 667,904 | 84,827 |

The candidate also used **18.2% more uncached input** than the pre-change
dispatcher. Cached input is already included in input; reasoning is already
included in output. These are actual native model counters, not retrieved-text
estimates or monetary costs. Repeated context contributes to input on each call.

### Task and repetition variation

| Task, both repetitions | Plain shell tokens | Pre-change tokens | Candidate tokens |
|---|---:|---:|---:|
| Conflict resolution | 212,749 | 229,567 | 241,755 |
| Nested interpolation | 152,631 | 236,225 | 235,809 |
| Pathname classification | 235,106 | 224,795 | 281,592 |

| Arm | Repetition 1 tokens | Repetition 2 tokens |
|---|---:|---:|
| Plain shell | 278,020 | 322,466 |
| Pre-change dispatcher | 374,388 | 316,199 |
| Candidate dispatcher | 397,628 | 361,528 |

The pre-change dispatcher beat plain shell in repetition 2, despite losing in
the aggregate. The candidate slightly beat the pre-change dispatcher on
interpolation, but lost on both other tasks. Two repetitions do not establish
statistical significance or a general ranking.

## Method and audit

[shell-manifest.json](shell-manifest.json) contains 18 fresh isolated trials:
three existing CPython repairs, three arms (plain shell, the pre-change
dispatcher, the new dispatcher), and two interleaved repetitions. Both skill
versions and their optional references are snapshotted and hashed. Every seed
failed its existing suite and matched the recorded source, tests and baseline
commit. All 18 agents were launched after the user's explicit approval, without
conversation inheritance or model/effort overrides, with at most three active.
Every recorded model context was `gpt-6.1-sol` with `medium` reasoning. The
baseline skill is pinned to `7e404af`; the candidate is the skill committed in
`fb384f7`. The pinned corpus remains CPython v3.14.0 at
`ebf955df7a89ed0c7968f79faec1de49f61ed7cb`, using Python 3.14.7 for grading.

The shared collector records actual input/output tokens, cached and uncached
input, model calls, and task-start-to-completion elapsed seconds. Elapsed time
includes model/tool waits and worker tests, not just retrieval. It independently
grades fixes and checks source scope, unchanged tests, method and model parity.
All three arms prohibited Context7 CLI and MCP retrieval. No engine was forced
just to produce tool calls. The manifest's call-site audit found `rg` in all six
trials per arm and none of the added tools. It found no literal MCP calls; the
collector found no retired MCP calls or Context7 CLI queries. Call-site evidence
is not a general JavaScript execution tracer or proof that every read influenced
the fix. Neither retired MCP namespace was available in the parent preflight.

[shell-results.json](shell-results.json) records `status: complete` and
`valid_comparison: true`. Every scope, skill-read, test-hash and model-parity
check passed. Per-response usage was deduplicated and reconciled to native
thread totals. Failed commands, additional reads, worker tests and final answers
remain counted. Parent preparation, scheduling, collection, grading and review
are excluded. Summed task time is the sum of individual agent durations, not
parallel-run wall time or retrieval-only latency. Shared caches, machine load
and scheduling affect both time and token comparisons.

Regrade retained artifacts with `python3 benchmarks/retrieval/shell.py collect`;
preparation and collection never launch agents. Preserve existing artifacts
before preparing another experiment. The earlier CLI report remains historical
evidence, not a fresh control group, and is not pooled with this run.

Validation: all 12 retrieval tests pass, including executable dispatcher examples
and rejection of incomplete/multiple benchmark turns, reversed timestamps and
forbidden CLI lookups. All 18 independently graded suites passed: 1,889 argparse
tests, 341 configparser tests with five skips, and 1,358 pathlib tests with 402
skips per corresponding trial. These familiar seeded one-/two-line repairs in
one repository cannot establish performance on structural discovery, unfamiliar
library contracts, architectural changes, other languages or Windows. The full
CPython suite and skipped platform-specific cases were not run.

**Decision:** retain `rg` as the default and keep `ag`/`ack`/AST routes conditional,
not mandatory. Do not describe the candidate as a token or speed optimization
based on this run. A future optimization should test a smaller instruction
surface on discovery-heavy tasks; adding more mandatory tool calls is not
supported by these measurements. No additional agents or unmeasured policy
changes were added after the approved 18 trials.
