# Retrieval dispatcher and Context7 CLI: clean repeated benchmark

The smaller retrieval dispatcher reduced total consumed tokens by **2.7% versus
the previous skill** in this run. Ordinary shell retrieval still used the fewest
tokens. Always requiring Context7 CLI documentation was more expensive on these
familiar local repairs, supporting conditional lookup rather than lookup on every
task. All 24 implementations passed independent grading.

## Actual model consumption

Each arm completed the same three CPython fixes twice, in fresh native workers
and isolated full checkouts. Neither Serena nor Context7 MCP was exposed in the
clean runtime; all 24 recorded zero calls to either backend.

| Arm | Passing trials | Model calls | Input + output tokens | Cached input | Uncached input |
|---|---:|---:|---:|---:|---:|
| Ordinary shell, no retrieval skill | 6/6 | 40 | 654,002 | 577,536 | 71,181 |
| Previous skill, retired-backend sentence removed | 6/6 | 50 | 831,552 | 727,040 | 97,910 |
| New dispatcher | 6/6 | 49 | 808,957 | 710,272 | 92,047 |
| Context7 CLI + shell, no retrieval skill | 6/6 | 56 | 1,012,696 | 894,464 | 109,885 |

The dispatcher used **6.0% less uncached input than the previous skill**, but
**23.7% more total tokens than ordinary shell**. Forced CLI verification used
**54.8% more total tokens than shell** and **25.2% more than the dispatcher**.
These are native model counters, not estimates of retrieved text. Cached input
is already part of input; reasoning is already part of output. No monetary
prices or cost-saving claim are applied.

### Repetition variability

| Arm | Repetition 1 tokens | Repetition 2 tokens |
|---|---:|---:|
| Shell | 327,979 | 326,023 |
| Previous skill | 403,987 | 427,565 |
| Dispatcher | 395,504 | 413,453 |
| Context7 CLI | 448,617 | 564,079 |

The aggregate improvement is not uniform across tasks. For conflict resolution,
the dispatcher used 271,398 tokens versus the previous skill's 266,617. For
interpolation it used 248,592 versus 214,257. Its pathname result, 288,967 versus
350,678, accounts for the overall saving. Two repetitions do not establish a
general efficiency improvement or statistical significance.

## Skill and setup changes

The [retrieval skill](../../llm/skills/code-retrieval/SKILL.md) now has a short
dispatcher and optional local-code/library-lookup references. It retains complete
relevant bodies, caller/test tracing, validation, error handling, source-version
verification, and stopping rules. Benchmark history and detailed procedures no
longer need to be read on every task. No additional retrieval wrapper was built.

Library lookup uses the official `ctx7` CLI: identify the dependency and target
version, resolve an actual documentation ID, query one unresolved contract, verify
the returned source, and keep a compact evidence record. Reuse the resolution;
never invent a version suffix or use MCP, login, API keys, or saved credentials.
The six forced CLI workers all received official Python 3.14 sources. Neither
skill arm needed a CLI query for these local fixes, so this experiment does not
measure the optional library procedure on unfamiliar dependencies.

Version 0.10.0 was installed privately at
`~/.codex-work/context7-cli/node_modules/.bin/ctx7`. Anonymous lookup was verified
with no API key or credential file at the effective XDG or legacy location.
Both writable Codex profiles have this directory as a PATH fallback for future
sessions; a configured-environment `ctx7 --version` check passed for each.
Normal installation uses the standard `~/.local` prefix. See the
[official CLI documentation](https://context7.com/docs/clients/cli).

The installer no longer installs the semantic backend or registers retrieval MCP
servers. Migration removes the old packages, state, registrations, and managed
hooks. Both agent families receive the same skill/references. The existing
version guard now checks literal CLI Bash requests, including reordered options;
it is not a general shell interpreter or proof that returned docs match a query.
Targeted migration preserves model, reasoning, permission, status-line, unrelated
hook settings, and existing RTK imports.

**Protected machine cleanup remains pending.** Both writable Codex registrations,
policies, skills, and hooks were updated. Project state and 18 old benchmark state
directories were removed. However, this sandbox cannot uninstall the packages
under `~/.local`, delete `~/.serena`, or update the two Claude profiles; their old
registrations still remain. Close the clients and run in an ordinary terminal:

```sh
bash /Users/odobrynin/dotfiles/llm/ai-install.sh --retrieval-only
```

Restart the clients afterward. That handles global CLI installation, retired
packages/global state, and managed profiles without upgrading unrelated tools.
Historical measurements and offline attribution support are preserved.

Six additional protected per-project state directories were identified. After
closing the clients, remove only their Serena metadata if completing the requested
state purge; this deletes saved backend state, not project source:

```sh
for project in flink-training Data-Engineering interview linux cv as24; do
  rm -rf -- "$HOME/$project/.serena"
done
```

Other nested project state was not exhaustively inventoried.

## Method and audit

The corpus is CPython v3.14.0, commit
`ebf955df7a89ed0c7968f79faec1de49f61ed7cb`: 5,220 tracked files and 1,032,831
Python lines. Tasks repair parser conflict resolution, nested cross-section
interpolation, and non-following file/directory classification. Implementation
paths were not supplied, but each prompt identified the native test module.
Repairs restore one or two implementation lines, not architectural changes.

All workers recorded `gpt-6.1-sol` with `medium` reasoning and no conversation
fork. At most three ran concurrently. Task/arm combinations were interleaved
with the second repetition ordered differently. Every workspace began at its
seeded local baseline, without upstream answer history. Every seed failed its
suite; every final fix passed the parent-run Python 3.14.7 native suite. Test
counts were 1,889 for argparse, 341 for configparser with five skips, and 1,358
for pathlib with 402 skips.

[cli-manifest.json](cli-manifest.json) records prompts, identities, fixture and
skill hashes, interpreter, setup commit, CLI version, and the MCP-free preflight.
[cli-results.json](cli-results.json) records per-response counters, session hashes,
patches, grades, model contexts, and method evidence. `status` is `complete` and
`valid_comparison` is `true`. All test hashes, baseline commits, permitted source
scopes, skill reads, and method checks passed.

The collector deduplicates response IDs and reconciles them with each session's
final thread totals. Failed attempts, worker tests, and final answers remain
counted. Parent setup, preflight, collection, grading, and review are excluded.
Call-site evidence is not a JavaScript execution tracer or proof that every
snippet influenced the fix. The [earlier contaminated attempt](CLI-BLOCKED.md)
is retained separately and excluded from every table above; the older MCP/tiny
fixture experiments are not pooled with this one.

Checks passed: 37 setup/version-guard tests, 10 retrieval tests, Bash syntax checks,
all 24 independent grades, writable Codex policy/hook/registration checks, local
documentation links, and final diff checks. Regrade retained artifacts with
`python3 benchmarks/retrieval/cli.py collect`; this never launches agents. A fresh
run requires preserving existing manifests/results first, new workspaces and
identities, and confirmation that neither backend is exposed in the runtime.

**Summary:** the refactor showed a small aggregate saving over the old skill;
plain shell remained best for these known local fixes. Context7 CLI supplies
versioned contract evidence, not demonstrated token savings here. Shared caches,
scheduling, two repetitions, one repository, familiar seeded repairs, and skipped
platform tests limit interpretation. Full machine migration, the full CPython
suite, unfamiliar library contracts, other repositories/languages, and Windows
execution were not validated by this run.
