# Archived CLI attempt: cached runtime contamination

This is the retained interrupted attempt. MCP tools were subsequently removed from
the runtime; see [the current follow-up](CLI.md) for the clean rerun.

The retrieval skill now dispatches between bounded shell reads, smart-read, and
an optional version-aware Context7 CLI lookup. The core no longer carries
benchmark history or semantic-backend setup. Optional local-code guidance retains
complete-body reads, caller tracing, validation, and error handling. Library
guidance resolves an actual documentation ID, verifies its source version, and
keeps a small evidence record without creating permanent task files.

Context7 uses the official `ctx7` CLI, not MCP. Version 0.10.0 was installed at
`~/.codex-work/context7-cli/node_modules/.bin/ctx7` and exercised anonymously.
No API key or credential file was present, including at the effective XDG config
location. The official [CLI documentation](https://context7.com/docs/clients/cli)
confirms that `library` and `docs` queries do not require login. The installer
uses the standard global CLI location for normal machine setup and never runs
`ctx7 setup` or login.

## Setup changes and remaining machine cleanup

The installer no longer installs the semantic backend or registers retrieval MCP
servers. Migration uninstalls the old packages, removes their registrations and
managed hooks, and clears the retired backend's state. Codex and Claude receive
the same dispatcher and optional references. The existing version guard now
checks literal `ctx7 docs` and library-qualified `ctx7 search` Bash commands.
It remains a request check, not a general shell interpreter or a guarantee that
returned documentation matches the requested version.

On this host, both writable Codex profiles have no `serena` or `context7` MCP
registration, have updated policy/skill files, and pass the managed-hook check.
The project's state and 18 retained benchmark state directories were removed.
Historical measurements, session logs, and offline attribution support remain;
they do not require the retired backend to be installed.

**Machine removal is not complete.** The sandbox cannot write to the installed
packages under `~/.local`, `~/.serena`, or either Claude profile. Both Claude
profiles still report retrieval MCP registrations. The old executable/state and
old Context7 MCP package also remain in these protected locations. No attempt
was made to bypass that boundary or change permissions.

Close running Codex/Claude agents and run from an ordinary terminal:

```sh
bash /Users/odobrynin/dotfiles/llm/ai-install.sh --retrieval-only
```

This targeted migration does not upgrade unrelated tools or change model,
reasoning, permissions, status-line selections, or unrelated hooks. It updates
the retrieval policies/references and guard, removes both legacy MCP entries,
installs `ctx7`, and uninstalls the retired packages/state. Restart the clients
afterward so cached tool schemas and instructions are gone. The normal installer
performs the same migration as part of its full setup.

## Attempted repeat benchmark

The planned comparison contains **24 fresh agents**: the same three CPython
v3.14.0 regressions, four arms, and two repetitions. Each workspace is a complete
5,220-file checkout with 1,032,831 Python lines. Source and test baselines match
the earlier large-repository experiment.

| Arm | Completed / planned | Independently passing | Retrieval-compliant |
|---|---:|---:|---:|
| Ordinary shell, no retrieval skill | 3 / 6 | 3 | 3 |
| Previous skill, without its retired-backend sentence | 4 / 6 | 4 | 4 |
| New dispatcher | 3 / 6 | 3 | 2 |
| Context7 CLI + ordinary shell, no retrieval skill | 4 / 6 | 4 | 4 |

All fourteen completed implementations passed the parent-run native test suite;
all tracked tests and baseline commits remained unchanged. However,
`/root/cli_symlinks_dispatcher_r1` obeyed a cached higher-priority runtime
instruction and called `mcp__serena__initial_instructions` once. It reported the
violation itself; the collector independently rejects it. Other completed trials
recorded no Serena or Context7 MCP calls. The forced CLI workers used anonymous
`ctx7 library` and `ctx7 docs` commands before completing their fixes.

Further launches stopped when the violation was discovered. Removing persisted
registrations did not remove tool names/instructions already loaded into this
session or inherited by its workers. Continuing would not establish a clean
"without Serena" comparison. Ten planned trials were therefore not launched.

The fourteen attempts consumed **1,884,572 actual input-plus-output tokens** in
total, including the contaminated trial and failed attempts. This is diagnostic
usage, **not an efficiency ranking**: arm counts are unequal and the dispatcher
contains a contaminated trial. One dispatcher worker's unsupported RTK command
and recovery also remain counted. No saving or general winner is claimed.

## Audit and checks

[cli-manifest.json](cli-blocked-manifest.json) retains exact task prompts, workspace
paths, hashes, skill versions, repeated-trial identities, and the blocking reason.
[cli-results.json](cli-blocked-results.json) retains every completed attempt, per-response
usage, model contexts, patches, grades, and method evidence. Its status is
`blocked` and `valid_comparison` is `false`. All recorded model contexts are
`gpt-6.1-sol` with `medium` reasoning. Parent setup, review, grading, and the
tool-availability preflight are excluded from measured worker consumption.

The collector reuses native counter validation: unique response IDs reconcile
with each session's final thread counters. Cached input is already in input;
reasoning is already in output. CLI call-site detection is not an execution
tracer, and skill-read checks are not proof of how every snippet influenced a fix.

Checks run:

```sh
python3 -m unittest llm.test_agent_config llm.test_context7_version_guard
python3 -m unittest discover -s benchmarks/retrieval -p 'test_*.py'
bash -n llm/ai-install.sh llm/smoke-test.sh
python3 benchmarks/retrieval/cli.py collect
```

The unit suites passed 37 setup/guard tests and 10 retrieval tests. Setup tests
include a mocked four-profile migration preserving custom model/permission
settings and unrelated hooks. The live writable Codex hook/registration checks
passed. A full machine smoke test and the protected-path migration were not run.

## Continue in a clean session

After the external migration and client restart, read this report and preserve
the blocked manifest/results under distinct archival names. Verify neither
backend is exposed in the new runtime, not merely absent from configuration.
Then run `python3 benchmarks/retrieval/cli.py prepare` for fresh, unfixed
workspaces and launch new native workers from its prompt files, with the recorded
names, no conversation fork, and at most three concurrent workers. Use a new
parent identity; never resume fixed or contaminated workspaces as fresh trials.

Run `cli.py collect` to grade and account for all 24 new trials. Compare matched
arms only after every method, test, source-scope, skill-hash, and model-context
check passes. Report total and uncached tokens separately, repetition variability,
and caller correctness. Two repetitions and small familiar seeded repairs still
do not establish statistical significance or cover unfamiliar library contracts,
architectural changes, other repositories, or Windows execution.
