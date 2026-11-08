# Large-repository benchmark: Serena and Context7 without the retrieval skill

Does a larger checkout change the token comparison? On 2026-11-08, nine fresh
native agents repaired three seeded regressions in complete CPython v3.14.0
checkouts. Context7 without the retrieval skill used the fewest total tokens in
this run. All nine final implementations passed independent grading.

| Strategy | Passing trials | Model calls | Input + output tokens | Cached input | Uncached input |
|---|---:|---:|---:|---:|---:|
| Skill-guided shell baseline | 3/3 | 21 | 383,166 | 333,440 | 46,315 |
| Serena, no retrieval skill | 3/3 | 35 | 662,087 | 594,048 | 62,991 |
| Context7 + ordinary shell, no retrieval skill | 3/3 | 18 | 333,175 | 271,104 | 58,364 |

Context7 used **13.0% fewer total tokens than the skill baseline** and **49.7%
fewer than Serena**. Serena used **72.8% more than the skill baseline**. These
are actual model-consumed input-plus-output counters, not estimates of retrieved
text. Cached input remains part of input; reasoning remains part of output.
Neither is added twice.

The uncached-input ranking differs: Context7 consumed **26.0% more uncached input
than the skill baseline**. Total-token savings therefore do not establish a
monetary saving. No prices or cost estimates are applied here.

## Repository and tasks

The source is [CPython v3.14.0](https://github.com/python/cpython/tree/ebf955df7a89ed0c7968f79faec1de49f61ed7cb),
commit `ebf955df7a89ed0c7968f79faec1de49f61ed7cb`. Its 5,220 tracked files
include 2,114 Python files containing 1,032,831 newline-counted lines, with
113,784,745 tracked bytes overall. Every trial received the complete checkout,
not an extracted source file or a repository padded with unrelated fixtures.

Prompts described behavior without giving implementation paths or line numbers.
Workers had to discover the implementation, trace callers and existing tests,
make the fix, run the native suite, and inspect their diff. The supplied test
command did identify the relevant test module equally in all arms.

| Seeded regression | Skill-only tokens | Serena-only tokens | Context7-only tokens |
|---|---:|---:|---:|
| Parser conflict resolution retains exhausted actions or drops surviving aliases | 129,844 | 212,655 | 112,458 |
| Nested cross-section interpolation uses the caller's lookup context | 124,205 | 255,111 | 112,772 |
| File and directory classification ignores non-following symlink requests | 129,117 | 194,321 | 107,945 |

The unmodified upstream suites passed before seeding. Each seeded baseline then
failed its suite, and every worker's fix passed a parent-run regrade. Native
test counts were 1,889 for `test_argparse`, 341 for `test_configparser` with five
skips, and 1,358 for `test_pathlib` with 402 skips. Grading used the same explicit
Python 3.14.7 executable and each checkout's `Lib` through `PYTHONPATH`.

The pathname and interpolation fixes restore two and one implementation lines,
respectively; conflict resolution restores one. This measures finding and fixing
narrow regressions inside a large repository, not designing a large change.

## Isolation and tool use

All workers recorded `gpt-6.1-sol` with `medium` reasoning. They started with
`fork_turns="none"`, without this conversation or the parent's earlier skill
read. Up to three workers ran concurrently, with task/strategy combinations
interleaved. Serena trials were kept sequential relative to one another to avoid
project-activation interference on the shared server.

Only the baseline workers were told to load the retrieval skill. Serena and
Context7 workers were explicitly told not to load or apply it, overriding the
shared policy's automatic-loading rule for these trials. Audit found one skill
read in each baseline and none in any of the six no-skill workers. Their runtime
still contained the shared general agent policy and the same available tools;
this did not remove tool schemas or create a skill-free runtime in every sense.

Serena workers used the existing server's symbol and reference tools on their
local source. Context7 cannot replace local source retrieval, so its workers
used ordinary shell tools locally and Context7 for documentation. All three
resolved and queried `/websites/python_zh-cn_3_14`; returned sources were the
official Python 3.14 Chinese documentation for the relevant modules. No sign-in,
dependencies, new server, explicit search index, or embeddings were needed.

All three skill workers and one Context7 worker also read Serena's mandatory
runtime manual; these initialization costs stay included. No such worker used
Serena for source retrieval. This uneven initialization, skill-loading overhead,
and different numbers of model calls can contribute to the observed differences.
There is no ordinary-shell-without-skill control, so the experiment cannot isolate
the benefit of Context7 itself from removing the skill and changing workflow.

Each workspace has a new local baseline commit containing its seeded regression,
without upstream history. Workers were forbidden to fetch upstream answers or
recover them from history. Grading checked the baseline commit, hashed all tracked
`Lib/test` paths and contents, and allowed only the intended implementation file
to change. Untracked Serena metadata was permitted but not application source.

## Accounting, checks, and artifacts

[large-manifest.json](large-manifest.json) records the exact prompts, identities,
paths, baseline hashes, repository size, and interpreter. [large-results.json](large-results.json)
records per-response usage, session hashes, model contexts, patches, independent
grades, and retrieval call-site evidence. Its `status` is `complete` and
`valid_comparison` is `true`: all nine trials passed grading and method/scope checks.

[large.py](large.py) reuses the existing collector's counter validation and
deduplication. Each session's unique response totals reconcile with its final
`thread_token_usage`. Failed attempts, initialization, implementation, worker
tests, and final replies remain included. Parent preparation, collection, grading,
and review are excluded. The call audit recognizes literal MCP calls and the
observed `ALL_TOOLS.find` selectors; it is not a general JavaScript execution
tracer or proof that every returned snippet influenced the implementation.

```sh
python3 -m unittest discover -s benchmarks/retrieval -p 'test_*.py'
python3 benchmarks/retrieval/large.py collect
```

The first command passed nine accounting/harness tests. The second independently
regrades and regenerates the results from retained workspaces and native session
logs; it never launches agents. Workspaces and upstream/seeded/final grade logs
remain under `/Users/odobrynin/.codex-work/retrieval-large-20261108/`.

For a fresh experiment, preserve these artifacts first. In a fresh harness
checkout without `large-manifest.json`, run `large.py prepare --base PATH --root
NEW_PATH --python PYTHON` with the clean pinned CPython checkout. Launch fresh
native agents from the generated prompts, with matching task names and no history
fork, then collect. Preparation refuses existing manifests and workspace roots;
do not reuse fixed trials or the legacy nested-CLI runner.

## Summary and limits

**In this large-checkout sample, Context7 without the retrieval skill beat the
skill-only baseline on total consumed tokens; Serena without the skill did not.**
The skill baseline still used the least uncached input. The earlier tiny-fixture
run tested skill-plus-tool arms instead, so its totals are not pooled with this
run or treated as a controlled before/after comparison.

There is one sample per task/strategy, one repository, familiar public APIs, and
only small seeded fixes. Shared caches, infrastructure, initialization, scheduling,
and platform-specific skipped tests limit interpretation. Repeated trials,
unfamiliar repositories, architectural changes, long-lived server reuse, other
languages, Windows execution, and the full CPython suite were not tested. No
statistical significance or general tool winner is claimed. Active profiles and
the retrieval skill were not changed.
