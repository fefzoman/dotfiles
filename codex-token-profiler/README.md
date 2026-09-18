# codex-token-profiler

A local, read-only CLI for understanding **where Codex tokens are going**.

It reads Codex rollout JSONL files from:

```text
$CODEX_HOME/sessions
$CODEX_HOME/archived_sessions
```

or `~/.codex` when `CODEX_HOME` is not set.

## What it reports

Exact values taken from Codex token telemetry:

- modern `token_usage_record` per-response usage, deduplicated by `response_id`
- cumulative `thread_token_usage` when present
- legacy `token_count` fallback for older sessions
- cumulative input tokens
- cached input tokens
- fresh input (`input - cached`)
- output tokens
- reasoning output tokens
- model calls
- current/last-call context vs model context window
- compactions

Estimated attribution:

- repository/file reads
- shell command output
- tests
- MCP/tool results
- file changes
- conversation/history
- `AGENTS.md` / instruction blocks
- compacted history
- platform/other context
- top commands by returned output
- top inferred files
- top individual model-visible payload generators

The **exact token totals are authoritative**. Attribution is intentionally approximate.

## Install

Python 3 and pip are required. The installer installs or upgrades the mandatory
`tiktoken` package before installing the command.

```bash
cd codex-token-profiler
./install.sh
```

This installs:

```text
~/.local/bin/codex-usage
```

Make sure `~/.local/bin` is on your `PATH`.

For zsh:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

`tiktoken` uses the `o200k_base` encoding for attribution estimates. Exact
Codex totals still come from rollout telemetry rather than token estimation.

## Usage

Show a compact report for the latest session:

```bash
codex-usage short
```

Analyze the latest session:

```bash
codex-usage current
```

List recent sessions:

```bash
codex-usage sessions
```

Analyze a specific session by UUID prefix:

```bash
codex-usage session 01a08a70
```

Or by rollout path:

```bash
codex-usage session ~/.codex/sessions/2026/09/17/rollout-....jsonl
```

Rank recent sessions:

```bash
codex-usage top --by session
```

Find noisy commands:

```bash
codex-usage top --by command --sessions 100
```

Find files most often injected through recognizable read/diff commands:

```bash
codex-usage top --by file --sessions 100
```

Machine-readable report:

```bash
codex-usage current --json
```

## Multiple Codex profiles

The tool honors `CODEX_HOME`.

Personal profile:

```bash
CODEX_HOME="$HOME/.codex" codex-usage current
```

Work profile:

```bash
CODEX_HOME="$HOME/.codex-work" codex-usage current
```

This matches setups such as:

```bash
alias codex-work='CODEX_HOME="$HOME/.codex-work" codex'
```

You can add:

```bash
alias codex-usage-work='CODEX_HOME="$HOME/.codex-work" codex-usage'
alias codex-usage-personal='CODEX_HOME="$HOME/.codex" codex-usage'
```

## Example

```text
CODEX TOKEN PROFILE
────────────────────────────────────────────────────────────────────────
Session                  01a08...
Project                  /Users/me/projects/app
Model                    gpt-5.6-sol / high

EXACT USAGE
────────────────────────────────────────────────────────────────────────
Input                    1.82M
Cached input             1.54M  (84.6%)
Fresh input              280.0K
Output                   71.0K
Reasoning output         48.0K
Model calls              27
Compactions              3

BY ACTIVITY — estimated cumulative input contribution
────────────────────────────────────────────────────────────────────────
Repository/file reads       610.0K
Shell command output         370.0K
Conversation/history         290.0K
AGENTS.md/instructions        95.0K
Tests                        180.0K
MCP/tool results             140.0K
Other/platform context       135.0K

TOP TOKEN GENERATORS — estimated model-visible payload
────────────────────────────────────────────────────────────────────────
 1.    93.0K  command output   pytest -vv
 2.    72.0K  command output   cat src/generated/schema.ts
 3.    48.0K  command output   git diff
```

## How attribution works

Codex provides exact cumulative token counters but does not provide a supported
"these 41,237 input tokens came from command X" field.

The profiler therefore:

1. Prefers modern per-response `token_usage_record` telemetry and deduplicates by `response_id`.
2. Falls back to increasing legacy `total_token_usage` counters when modern records are absent.
3. Reconstructs visible retained context from `response_item` records.
4. Uses the actual model-visible tool output records for shell/tool attribution.
5. Estimates the token footprint of each visible context source.
6. For each model call, attributes exact input tokens to visible sources that
   were resident before that call.
7. Assigns unexplained residual input to `Other/platform context`.
8. Resets retained-history estimation when a compaction replacement is recorded.

Important: the tool deliberately does **not** attribute the full untruncated
`event_msg/item_completed` stdout to the model. Current Codex rollouts may
persist the same stdout multiple times while the model-visible
`function_call_output` / `custom_tool_call_output` is smaller.

## Interpretation

### Input vs cached input

`cached_input_tokens` is a subset of `input_tokens`.

So:

```text
fresh input = input - cached input
```

Do not calculate `input + cached input`.

### Current context vs cumulative usage

A session can show:

```text
current/last-call context: 110K
cumulative input:          1.8M
```

That is normal. Cumulative usage grows across model calls while the current
context is bounded by the model window and may be compacted.

### Why "top generator" differs from cumulative contribution

A 20K-token test log injected once can remain in context for ten subsequent
model calls. Its one-time payload is ~20K, but its cumulative input contribution
can be much larger, usually mostly cached.

## Safety / privacy

The tool is local and read-only:

- does not modify Codex sessions
- does not call OpenAI APIs
- does not upload rollout contents
- does not execute commands found inside rollouts
- prints local commands/file names only to your terminal

`--json` can contain local paths and command strings, so treat exported reports
as potentially sensitive.
