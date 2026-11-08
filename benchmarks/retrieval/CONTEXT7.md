# Does Context7 earn a place for external API questions?

**This experiment found no net benefit to justify keeping Context7 in the default
retrieval workflow.** It tested version-sensitive external contracts, not local
repairs. Both strategies answered every question correctly, but Context7-first
used more total tokens and more elapsed time in all three version cases. Even
the explicitly indexed version needed direct-source fallback to settle the
whole contract. This is negative evidence for this workload, not proof that
Context7 can never be useful.

## Questions and independent evidence

The first two cases were fixed before looking at Context7's library results:

* **FastAPI 0.118.0:** dependency cleanup timing while a StreamingResponse uses
  the yielded session, and whether that release accepts `Depends(scope=...)`.
* **Zod 4.1.12:** required enum record keys, the partial-record API, rejection of
  invalid keys/values, and the relevant Zod 3 difference.

The resolver then showed no indexed FastAPI versions and no Zod 4.1.12 index.
Before any Context7 document query or worker result, a separate **Zod 4.0.1
best-case cohort** was registered because Context7 explicitly listed that
version. It asks the same record question; it is not a third independent library
contract. No original case was discarded or replaced.

The independent rubric used [FastAPI's tagged dependency documentation](https://github.com/fastapi/fastapi/blob/0.118.0/docs/en/docs/advanced/advanced-dependencies.md),
the [tagged Depends constructor](https://github.com/fastapi/fastapi/blob/0.118.0/fastapi/params.py),
and the [official scope-introduction history](https://fastapi.tiangolo.com/advanced/advanced-dependencies/#dependencies-with-yield-and-scope).
Zod facts were checked against tagged documentation, tests and implementations,
including the [4.1.12 record tests](https://github.com/colinhacks/zod/blob/v4.1.12/packages/zod/src/v4/classic/tests/record.test.ts)
and [4.0.1 record tests](https://github.com/colinhacks/zod/blob/v4.0.1/packages/zod/src/v4/classic/tests/record.test.ts).
Pinned source snapshots and hashes are recorded in the manifest. Packages were
not installed, and no library runtime tests were executed.

## Actual model consumption and task time

Each case ran twice per arm in fresh native agents. Direct lookup could use web
or shell tools against official documentation/tagged source. Context7-first
used the anonymous CLI to resolve a real library ID and query documentation,
then checked version coverage and used direct official-source fallback if needed.
That fallback was allowed, not automatically required after every CLI query.

| Case, both repetitions | Direct tokens | Context7-first tokens | Token change | Direct time | Context7-first time |
|---|---:|---:|---:|---:|---:|
| FastAPI 0.118.0 | 143,259 | 184,648 | +28.9% | 57.57 s | 71.79 s |
| Zod 4.1.12 | 161,855 | 191,923 | +18.6% | 70.01 s | 90.10 s |
| Indexed Zod 4.0.1 | 159,526 | 238,950 | +49.8% | 74.96 s | 108.82 s |

Context7-first increased summed task time by **24.7%, 28.7% and 45.2%**,
respectively. The preregistered retention criterion was a repeatable, at least
10% aggregate token or time benefit in a case, without a correctness/version
loss. No case met it. The small 2.9% token advantage in the first Zod 4.1.12
repetition disappeared in the second; it is not a repeatable saving.

| Case | Direct tokens, r1 / r2 | Context7 tokens, r1 / r2 |
|---|---:|---:|
| FastAPI 0.118.0 | 81,967 / 61,292 | 92,552 / 92,096 |
| Zod 4.1.12 | 99,145 / 62,710 | 96,277 / 95,646 |
| Indexed Zod 4.0.1 | 98,889 / 60,637 | 120,702 / 118,248 |

Both arms achieved **6/6 fully correct, version-supported answers**. There were
no excluded workers, retried workers or credential/sign-in attempts.
Context7-first made **36 model calls versus 27** for direct lookup. Each Context7
worker resolved its library once; the indexed Zod workers reused that resolution
for a second documentation query rather than resolving it again.

Uncached input was not uniformly worse: FastAPI used 40,126 uncached tokens with
Context7 versus 42,428 directly, a **5.4% reduction**. But its total tokens and
time were still higher. For Zod 4.1.12, uncached input rose from 17,638 to 21,656;
for indexed Zod 4.0.1, from 16,899 to 40,441. No monetary saving is inferred.

For accounting only, the three-case totals were 464,640 tokens and 202.53 summed
seconds directly, versus 615,521 tokens and 270.71 seconds for Context7-first.
Do not treat the duplicated Zod contract as independent evidence in a general
tool ranking. Cached input is already included in input, and reasoning is
already included in output; neither is added twice.

## What Context7 supplied, and why workers still used direct sources

FastAPI resolved to `/websites/fastapi_tiangolo` without indexed versions. Its
snippets included current scope APIs as well as historical behavior, so workers
checked the exact 0.118.0 tag. Zod 4.1.12 was absent from the returned version
list; base-library queries returned main-branch documentation and could not
establish exact-patch behavior. Workers verified that tag directly.

The best-case `/colinhacks/zod/v4.0.1` queries did return URLs tagged v4.0.1.
That demonstrates a real capability: version-qualified snippets and source
links. But those snippets did not settle all required partial-record key/value
failure cases. Both workers queried again, then checked the tagged parser and
tests. All six Context7 workers disclosed fallback. Useful initial snippets did
not translate into a measured correctness, token or latency advantage here.

## Audit and limitations

[context7-evidence-manifest.json](context7-evidence-manifest.json) records exact
prompts, preregistration, the added indexed-version cohort, resolver metadata,
the retention criterion, ground truth and source snapshot hashes.
[context7-evidence-results.json](context7-evidence-results.json) records all
answers, grades, CLI method evidence, counters, elapsed time and session hashes.
It reports `complete: true` and `valid_comparison: true`.

All twelve workers used `gpt-6.1-sol` with `medium` reasoning, no conversation
inheritance or overrides, and at most three workers active. Literal tool calls
confirmed the required CLI commands and absence of skill/MCP retrieval. The
anonymous preflight checked that no key or credential file was configured,
without reading secrets. CLI version was 0.10.0. No Context7 MCP was initialized.
Call-site checks are not a general shell/JavaScript execution tracer; answers
and cited official evidence were also reviewed.

Native response IDs were deduplicated, and usage totals reconciled to thread
counters. Task elapsed time includes model/tool waits, reads, version checks and
the final answer, not just backend response latency. Parent preparation,
preflight, oracle lookup, collection and review are excluded. Strategy-specific
instruction overhead remains included. All seventeen retrieval harness tests pass,
including typed-fact grading and rejection of spoofed source hosts and version
prefixes.

Only two API contracts and two repetitions were tested. Related Zod cases,
shared caches, parent source prefetching and scheduling limit generalization.
Resolution reuse across a long session, hard-to-discover documentation, other
libraries, offline availability and implementation tasks were not measured.
No claim of statistical significance or universal tool uselessness is made.

**Recommendation:** do not restore a mandatory Context7 route or justify a
default-install dependency from this evidence. Keep direct official-source
lookup as the default. A future retention argument needs a concrete workload
where Context7 beats that baseline; its advertised capability alone is not proof
of value. No skill, installer, installed profile or CLI was changed by this test.
