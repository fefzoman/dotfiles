# token-profiler

Local, read-only token and optimization reporting for Codex and Claude Code.

## Profiles

The required first subcommand selects both the agent and its fixed profile:

| Selector | Home | Session files |
|---|---|---|
| `codex` | `~/.codex` | `sessions/`, optionally `archived_sessions/` |
| `codex-work` | `~/.codex-work` | `sessions/`, optionally `archived_sessions/` |
| `claude` | `~/.claude` | `projects/` and companion subagents |
| `claude-work` | `~/.claude-work` | `projects/` and companion subagents |

Use `--home PATH` after the selector to inspect a nonstandard profile.

## Install

The installer requires Python and pip, installs the mandatory `tiktoken`
dependency, installs `~/.local/bin/token-profiler`, and removes the obsolete
`~/.local/bin/codex-usage` command.

```bash
cd llm/token-profiler
./install.sh
```

## Usage

Without a report action, the latest full report is shown:

```bash
token-profiler codex
token-profiler codex-work
token-profiler claude
token-profiler claude-work
```

Each profile supports the same actions:

```bash
token-profiler codex short
token-profiler claude current
token-profiler codex sessions --archived
token-profiler claude session SESSION_ID
token-profiler codex top --by session
token-profiler claude top --by command --sessions 100
token-profiler codex current --json
```

## Exact Usage

Codex accounting uses modern `token_usage_record` telemetry with cumulative
`thread_token_usage` when available, and increasing legacy `token_count`
counters as a fallback.

Claude accounting sums each unique assistant message's usage:

```text
total input = input_tokens
            + cache_creation_input_tokens
            + cache_read_input_tokens
```

The report keeps cache reads and cache creation separate. Reasoning is exact
only when the agent records a dedicated reasoning/thinking counter.
Companion `SESSION_ID/subagents/*.jsonl` usage is included in the parent Claude
session, and the combined timeline determines the current inner session.

Reported exact fields include:

- total, cached, fresh, and cache-creation input
- output and available reasoning output
- model calls and compactions
- current/last-call context when the session records a context window
- current inner-session usage

## Inner Sessions

One JSONL file is an outer session. The current inner session is the latest
contiguous activity window in that file:

- a gap of 30 minutes or less remains in the same inner session;
- a gap greater than 30 minutes starts a new inner session.

The full, short, and JSON reports include exact token, call, compaction, start,
end, and elapsed-time statistics for the latest inner session.

## Optimization

Optimization measurements retain their original scopes and are never summed:

- exact provider cache reuse for the outer and inner session
- estimated project-level RTK shell-output savings
- Headroom's global durable savings ledger
- observed Serena and Context7 call counts and estimated result payload
- per-tool call/result totals, averages, maxima, and payload share
- tool-result outliers over 2K tokens with arguments and repeated-query markers
- largest model calls ranked by both total and fresh input
- model-call gaps and cold-prefix causes (start, idle resume, compaction, or
  indistinguishable cache-expiry/prefix changes)
- per-work-window resume context, first-call cold cost/share, and later-call
  fresh-input total/average
- Ponytail plugin/policy state

Serena and Context7 calls made through Codex's programmatic `exec` wrapper are
reported as lower bounds because loop multiplicity is not stored separately in
the rollout. A `0` means no matching direct call or programmatic invocation was
recorded; it does not mean that the tool is unavailable.
Ponytail savings are not calculated because avoided work is not observable in
session telemetry.

## Estimated Attribution

The profiler uses `tiktoken` with `o200k_base` to estimate activity, command,
file, tool, instruction, history, and payload contributions. Exact provider
usage remains authoritative; attribution is diagnostic rather than billing
data.

Payload is reported in three views: all historically observed transcript
items, items still active after the latest compaction, and their estimated
difference. Instruction sources are separated when the rollout preserves a
recognizable boundary such as AGENTS.md, Ponytail, permissions, or the skills
catalog.

## Safety

The profiler:

- reads local session files without modifying them;
- makes no OpenAI or Anthropic API requests;
- uploads no transcript data;
- never executes commands stored in a session.

JSON output can expose local paths, prompts, tool arguments, and command
strings. Treat it as sensitive.
