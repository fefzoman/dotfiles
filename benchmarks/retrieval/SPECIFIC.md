# Which added search tools earned a place?

The earlier repair benchmark did not exercise the added tools. This follow-up
tests their intended jobs instead: equivalent text searches for `ag`/`ack`, and
syntax-aware retrieval for `ast-grep`. The resulting decision is to **remove
ag/ack from the dispatcher and installers**, and retain **only a narrow,
optional ast-grep route for verified structural file discovery**. Ordinary text
search remains `rg`.

## Equivalent text searches: remove ag and ack

Three CPython text-search tasks covered a known file, recursive content search
across `Lib`, and Python-only filename discovery. Each command warmed up once,
then ran nine times in rotated order. An independent scan of tracked `.py`
files checked every returned filename, line number and matching line. All
measured results were complete and equivalent after normalizing columns/order.

| Task | Matches | rg median | ag median | ack median |
|---|---:|---:|---:|---:|
| Literal `shell=True` in test_subprocess.py | 10 lines | 33.6 ms | 126.5 ms | 84.0 ms |
| Literal `follow_symlinks` across Lib | 410 lines | 82.7 ms | 176.0 ms | 405.8 ms |
| Python filenames containing ExtendedInterpolation | 2 files | 82.6 ms | 172.9 ms | 384.8 ms |

There was no returned-context token saving. With `o200k_base`, the normalized
results contained 208, 10,668 and 12 tokens respectively, identically for each
tool. Raw `ack` output matched `rg`'s counts. Raw `ag` output contained 228,
12,894 and 12 tokens because of columns and repeated same-line matches. These
are output-token counts, **not total model consumption**. No native-agent token
benchmark is claimed for ag/ack; identical context and slower commands gave no
reason to add their instruction and dependency overhead.

The working recipes account for piped agent stdin: `ack --no-filter` and
`ag --vimgrep`. An initial `ag -l` recipe returned no filenames and was rejected
by the oracle before measurement. Full commands, versions, samples, source
hashes and tokenizer version are in
[specific-text-results.json](specific-text-results.json). Reproduce with
`python benchmarks/retrieval/specific_text.py` using the existing token-profiler
Python environment, after preserving the current output. No dependency was added.

## Ad-hoc structural queries: ast-grep did not help

Fresh agents answered two exact retrieval questions on real CPython source:
all calls with a direct literal `shell=True` keyword, regardless of keyword
order or multiline layout; and all `assertRaises` calls whose first positional
argument is exactly `ValueError`. Strings/comments and nested-call ownership
were explicitly covered. Python's standard-library AST independently supplied
the expected call-start lines (seven and fifteen matches).

| Task, two repetitions | Shell/Python tokens | ast-grep tokens | Shell/Python time | ast-grep time |
|---|---:|---:|---:|---:|
| Direct shell=True calls | 73,920 | 118,941 | 46.75 s | 47.88 s |
| First argument ValueError | 63,971 | 108,968 | 35.49 s | 51.58 s |

Every eligible answer was correct. The ast-grep workers used it to enumerate
call nodes, filtered and verified with Python AST, and read installed help.
They did not discover the narrowest possible rule. That is a measured cost of
ad-hoc use, not proof that ast-grep cannot express the queries. Parent checks
also found that intuitive positional patterns missed valid keyword layouts.
This evidence does not support routing ordinary syntax questions to ast-grep
or dumping full AST JSON into model context.

## Verified structural file discovery: retain one optional route

One more task tested an already-verified query, rather than query learning:
find files in `Lib/asyncio` containing a bare exception handler, excluding
comments/strings. Both arms received a complete executable recipe and returned
the same six filenames. The ast-grep rule combines `except_clause` node kind
with `^except\s*:` and emits only filenames. The baseline walks Python ASTs
using the pinned Python 3.14.7 interpreter.

| Prepared query, two repetitions | Model calls | Total model tokens | Uncached input | Summed task time |
|---|---:|---:|---:|---:|
| Standard-library Python AST | 4 | 48,366 | 2,841 | 21.05 s |
| ast-grep, filenames only | 4 | 47,841 | 3,593 | 18.86 s |

The prepared ast-grep query was faster in both repetitions: 8.619 vs 10.459
seconds and 10.243 vs 10.586 seconds. Summed time fell **10.4%**. Total tokens
fell only **1.1%**, while uncached input **rose 26.5%**. The output itself was
identical (51 normalized output tokens); the small total-token difference is
consistent with recipe/prompt size and repeated context, not compression or a
reliable cost saving. Two repetitions are insufficient for statistical significance.

An interleaved nine-repeat command check, using pinned Python 3.14.7, measured
**200.0 ms for Python AST versus 67.5 ms for ast-grep**. It verified exactly the
same filenames. This narrower command-level gain supports keeping a prepared,
filenames-only route, not a general performance claim. Commands and samples are
in [specific-ast-ready.json](specific-ast-ready.json); the initial unversioned
parent measurement is retained separately inside that artifact.

## Accounting, exclusions and resulting change

[specific-manifest.json](specific-manifest.json) retains prompts, expected
answers, source hashes and agent identities.
[specific-results.json](specific-results.json) records native usage, elapsed
time, answers, correctness/method checks and session hashes. All twelve eligible
trials passed the independent oracle and method checks, using `gpt-6.1-sol`
with `medium` reasoning, without conversation inheritance or model overrides.
At most three agents were active. Tokens are actual input plus output; cached
input and reasoning are not added again. Task time includes model/tool waits.
Parent preparation, grading, command experiments and review are excluded.

Three additional trials remain recorded but are excluded from comparisons:
one shell worker read a forbidden skill; two prepared Python recipes failed
because fresh workers resolved `python3` to Python 3.9, which could not parse
the corpus's match statements. Fresh replacement workers used the same retrieval
prompt or the pinned compatible interpreter, respectively. The exclusions used
**160,956 tokens**; eligible trials used **462,007**, for **622,963 actual tokens**
across all fifteen workers. None of that failed work is hidden or pooled into
the clean comparison.

The main dispatcher is now 258 words and has no ag/ack commands or generic
ast-grep call-pattern recipe. The optional structural reference documents the
verified rule, filenames-only output, compatible-parser validation, and read-only
constraints. Both policy templates keep rg/sed and smart-read as normal routes.
Installers and the active tool inventory no longer include ag/ack; historical
benchmark records remain unchanged. Existing Homebrew binaries are outside this
sandbox's writable paths and were not uninstalled. Installed agent profiles were
not changed during this session.

Validation: all fifteen retrieval tests and Bash syntax checks passed. The tests
exercise the documented filename query against real syntax, typed handlers,
comment/string decoys, piped stdin, and the independent oracle's edge cases.
These are targeted retrieval tasks, not implementation or architectural-change
benchmarks. Warm caches, shared load, one language/repository, known paths and
only two model repetitions limit extrapolation. The final full dispatcher was
not rerun through the unrelated seeded-repair benchmark; no whole-skill token
saving is claimed.
