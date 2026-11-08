# Shell-first retrieval dispatcher: command measurements

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

## Model-token experiment: prepared, not run

[shell-manifest.json](shell-manifest.json) contains 18 fresh isolated trials:
three existing CPython repairs, three arms (plain shell, the pre-change
dispatcher, the new dispatcher), and two interleaved repetitions. Both skill
versions and their optional references are snapshotted and hashed. Every seed
failed its existing suite and matched the recorded source, tests and baseline
commit. No benchmark agents have been launched; explicit authorization is pending.

The shared collector records actual input/output tokens, cached and uncached
input, model calls, and task-start-to-completion elapsed seconds. Elapsed time
includes model/tool waits and worker tests, not just retrieval. It independently
grades fixes and checks source scope, unchanged tests, method and model parity.
All three arms prohibit Context7 CLI and retired MCP retrieval. No engine is
forced just to produce tool calls; if the dispatcher never selects AST search,
the run will not demonstrate its benefit on structural discovery.

[shell-results.json](shell-results.json) explicitly records zero completed trials
and `valid_comparison: false`. Those zero counters are missing measurements, not
zero-cost executions. No model-token or end-to-end performance saving is claimed.
The earlier CLI report remains historical evidence, not a fresh control group.

After authorization, launch each manifest prompt in a fresh native agent without
conversation inheritance or model/effort overrides, with at most three active.
Remove the pending-authorization `blocked_reason` when starting. Collect with
`python3 benchmarks/retrieval/shell.py collect`; preparation and collection never
launch agents. Preserve existing artifacts before preparing another experiment.

Validation: all 12 retrieval tests pass, including executable dispatcher examples
and rejection of incomplete/multiple benchmark turns, reversed timestamps and
forbidden CLI lookups. Full model trials and unfamiliar-library contracts have
not been measured. These familiar seeded one-/two-line repairs also cannot
establish performance on architectural changes or other repositories.
