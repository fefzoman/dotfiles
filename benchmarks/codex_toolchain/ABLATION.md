# Toolchain ablation: uv setup

The main remaining overhead came from instructions and tool declarations sent eagerly, rather than the availability of MCP servers. After removing that eager context in an isolated profile, the toolchain kept native web search, Serena, Context7, code-index, RTK, and read hints. It used **20,774 uncached input plus output tokens**, compared with **19,701** for a successful pure-Codex control with web enabled: a 5.45% gap. Both made 13 model requests and passed independent dependency checks.

These are local observations for GPT-6.1 Sol at medium effort on Codex CLI 0.165.0, not a general performance guarantee. The [machine-readable results](ablation-results.json) include every measured variant, validation commands, transcript paths, and cache observations.

## Exact startup costs

Twenty-eight verified single-response probes used the same working directory and prompt: `Reply with exactly READY. Do not use tools.` Each made exactly one model request. The full startup control repeated at 18,072 input tokens. Cumulative removals account for the entire 7,028-token difference from the earlier pure baseline:

| Remove in sequence | Startup input remaining | Additional tokens removed |
|---|---:|---:|
| Full updated toolchain | 18,072 | — |
| Native web-search declaration | 15,616 | 2,456 |
| Automatic skills catalog | 13,529 | 2,087 |
| Global AGENTS.md | 12,513 | 1,016 |
| Ponytail startup instructions | 11,802 | 711 |
| DLM startup instructions | 11,492 | 310 |
| App-install recommendations and their tool | 11,044 | 448 |
| Remaining plugins, MCP servers, hooks, and baseline feature flags | 11,044 | 0 |

These are **input tokens**, usually cached after startup, rather than fresh tokens charged on every request. The Ponytail and DLM rows follow removal of the catalog; independent removal also removes their catalog entries and saved 1,299 and 508 startup tokens respectively. Adding those independent savings to the catalog saving would count some tokens twice.

The earlier pure baseline disabled native web search, while the full toolchain kept its 209-line declaration. That capability mismatch contributed 2,456 startup tokens. With web enabled on both sides, the pure and lean probes each used exactly **13,500** startup input tokens. Serena, Context7, code-index, and RTK/read-hint hooks remained available in the lean probe.

Some CLI-only removals did not actually remove component instructions in this runtime. Those exploratory probes were excluded from the verified set. The verified tests changed isolated configuration files, removed the global AGENTS.md file when appropriate, and checked the emitted prompt. One all-hooks-off probe also omitted remote skill entries, so its independent difference should not be treated as the isolated size of hook instructions; the cumulative measurements above separate those effects.

## Full task replays

Each replay started from `flink-training` commit `d46a23d` plus the same Docker Compose patch, in a disposable checkout with a separate uv cache. It received the same three prompts, sequentially: `Create uv for this project`, the same prompt again, then `.venv was not created`. Original interrupted timing was not reproduced. Two sequential replay batches overlapped; timing comparisons are not causal findings.

| Configuration | Model requests | Uncached input + output | All input + output, including cached | Checks |
|---|---:|---:|---:|---|
| Pure, web on — successful repeat | 13 | 19,701 | 322,549 | Pass |
| Pure, web off | 21 | 21,702 | 462,790 | Pass |
| Full updated toolchain | 24 | 28,475 | 708,923 | Pass |
| Remove catalog only | 22 | 41,538 | 744,258 | Pass |
| Remove Ponytail only | 23 | 54,782 | 703,870 | Pass |
| Remove global AGENTS.md only | 23 | 33,006 | 779,374 | Pass |
| Remove Context7 only | 23 | 49,941 | 674,453 | Pass |
| Remove DLM only | 25 | 55,823 | 790,671 | Pass |
| Remove read-hint hook only | 23 | 31,004 | 697,116 | Pass |
| Disable web only | 21 | 64,844 | 587,980 | Pass |
| Pure, web on — first attempt | 15 | 36,039 | 377,799 | Fail |
| Remove RTK policy and hook | 25 | 61,710 | 733,198 | Pass |
| Lean, web off | 12 | 29,062 | 231,814 | Pass |
| Lean, web on | 13 | 20,774 | 277,542 | Pass |

All checkouts independently ran `uv sync --locked --offline`, imports of the original dependency packages including `pyflink.table.TableEnvironment`, a Python 3.12 check, and `uv pip check`. Thirteen of fourteen replays passed. The first pure-with-web attempt moved PyFlink to an optional group and failed the default-environment import check. It remains in the results as a failed trial; its repeat passed.

A single removal did not reliably lower whole-task consumption. The catalog-free worker, for example, retrieved more documentation later. The full control made two Context7 calls and a web search; the successful pure-with-web repeat completed without those Context7 calls. Removing RTK was verified to eliminate RTK from every shell command, but did not improve total tokens in that sample. The lean profile showed that productive tools can stay available without eager catalogs and startup policy blocks.

## What the earlier totals hid

The unchanged full-toolchain control used 28,475 uncached-plus-output tokens here, versus 56,407 in the previous replay. Large drops in cache reuse account for much of the variation; the transcripts do not establish whether those drops came from server cache behavior or an unrecorded change in request construction. Removing a component can reduce total input while its run still has a higher uncached total. The per-response usage records were reconciled with cumulative totals rather than adding resumed-turn totals together.

The lean-with-web run processed 277,542 total tokens versus 322,549 for its successful pure-with-web control, despite using 1,073 more uncached-plus-output tokens. That is close to pure Codex for this task while retaining the named MCP and shell tools. It does not prove the same result for every workload.

The measured direction is to keep useful tools deferred and make general skills and plugin policies opt-in. DLM belongs in the work profile. Native web must be matched when comparing configurations. Shortening a global policy is an option to test separately; this experiment removed it, and does not establish that project-specific requirements can safely be removed.

No global settings changed during this investigation. The lean profiles disabled app integrations and omitted global AGENTS.md; they were diagnostic profiles, not production replacements. Raw logs and runners remain under the artifact directory recorded in the JSON. Docker pipelines and Claude model sessions were not tested.
