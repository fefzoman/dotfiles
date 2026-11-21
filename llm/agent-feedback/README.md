# agent-feedback

A coding agent can lose ten minutes retrying a command that isn't installed, or
re-read the same file five times in one turn. Usage totals show that a session
was expensive, but not why. `agent-feedback` looks at what agents actually did
(which tools they called, what failed, how much output came back) and turns
recurring patterns into findings with concrete fixes.

It works with both Claude Code and Codex, in personal and work profiles. The
CLI has no dependencies and runs entirely on the local machine: analysis is
deterministic and makes no network or model requests.

There are two ways to feed it:

- **`scan`** reads every local transcript on demand. It needs no setup and
  stores nothing, which makes it the right starting point.
- **Hook collection** records allowlisted metadata as sessions run, for
  repositories you opt in. It keeps a seven-day history that `analyze`,
  `report` and `propose` work from.

## Install

The full `llm/ai-install.sh` installs the package with `uv tool` and Python
3.13 (the package itself requires Python 3.12 or later). It also merges
collection hooks for this dotfiles worktree into all four profiles. To install
only the CLI:

```sh
uv tool install --python 3.13 --reinstall llm/agent-feedback
```

This provides two commands: `agent-feedback` and `agent-feedback-install-hooks`.
Reinstall after changing the source, because `uv tool` installs a copy.

## Scanning all sessions

```sh
agent-feedback scan                       # markdown report
agent-feedback scan --format json         # full findings and evidence
agent-feedback scan --details             # name executables and files
agent-feedback scan --since 2026-11-21    # only activity from this date on
```

`scan` reads Claude transcripts (`~/.claude*/projects`) and Codex transcripts
(`~/.codex*/sessions` and `archived_sessions`) in every profile and applies the
rules in memory. Nothing is written to disk, so `propose` can't use scan
findings.

Findings are ranked by cost, measured two ways. **Tokens** are those of the
model replies that issued the flagged calls, cache reads included. **Time** is
the gap until the next call, with idle gaps over five minutes left out. One call
can trigger several rules, for example an oversized output inside a long turn,
so finding costs overlap and don't add up to the total.

### Rules

| Rule | Triggered when | Treated as |
|---|---|---|
| `missing_executable` | a shell call exits with 127 or prints `command not found` | suspected cause |
| `repeated_command_failure` | the same command fails three times in a session with no success in between | suspected waste |
| `repeated_read` | the same file range is read again with no edit to that file in between | suspected waste |
| `oversized_output` | a tool result exceeds 20 KB, which every later model call re-sends | suspected waste |
| `long_turn` | one user turn needs more than 50 tool calls | observation |
| `permission_friction` | a session shows at least three approval requests (hook data only) | observation |
| `collection_gap` | the collector recorded rejected or missing telemetry | outcome unverifiable |

Two blind spots come from the transcripts themselves. Claude transcripts carry
no exit codes, so for Claude only `command not found` errors are classified as
missing executables. Codex reads files through the shell rather than a read
tool, so re-reads are detected for Claude only.

### Suggested fixes

A finding alone says something is wrong. The **Suggested fixes** section at the
top of the report says what to change, ranked by cost. Each suggestion names a
target:

- **environment**: install a tool, fix a prerequisite or a permission;
- **instructions**: add guidance to the repository's `CLAUDE.md` and `AGENTS.md`;
- **request**: change how the task is asked, for example splitting it up.

Suggestions use the evidence behind each finding, not a fixed sentence per rule.
Missing executables are checked against the current shell's `PATH`.
Repeated failures are matched to the kind of error first seen (permission,
missing file, timeout, wrong arguments, failing test). Oversized outputs are
grouped by tool, because the fix for a large `Read` (page through it) differs
from the fix for a noisy shell command (filter it).

Long turns usually cost the most, so they're split by tool mix:

| Turn type | What dominates the turn | Suggested direction |
|---|---|---|
| failing | at least a third of the calls fail | fix the failing prerequisite first |
| remote | cloud CLIs, containers and polling loops | wrap recurring queries in a script or skill |
| exploration | reads and searches | keep a codebase map, name files in the request, delegate the search |
| edit-and-rerun | edits mixed with repeated runs of a check | run the narrowest check and read the first failure |
| broad | none of the above | split the request or agree on a plan first |

Re-reads are told apart by location. A repository file that keeps being
re-read belongs in the codebase map. A saved tool output should be searched
instead of re-read. A background task's output file grows while the task runs,
so re-reading it is polling: the fix is to wait for the completion notification.

These thresholds were tuned on local transcripts. They are heuristics that
point at a likely cause, not proof of one.

### Names stay out of the report by default

Transcripts contain commands, paths and sometimes secrets. By default the
report contains none of them: shell commands are labelled only with fixed
families (read, remote, wait, run), errors with fixed kinds and files with a
location. Because those labels come from the commands themselves, the turn
breakdown works for Codex as well, even though Codex runs everything through
the shell.

`--details` adds executable names, the next word when it looks like a
subcommand (as in `git diff`), and file paths, so a suggestion can say "`ruff` is not on PATH"
instead of "rerun with --details". It never shows arguments, and it still
stores nothing.

### Checking whether a fix helped

Save a report when you apply a fix, then scan again later from the date of the
fix:

```sh
agent-feedback scan > ~/before-fix.md
# ...apply the fix, work normally for a few days...
agent-feedback scan --since 2026-11-21
```

With `--since`, only tool calls and model replies from that moment on count,
and transcripts last modified earlier are skipped. A date without an offset
means local midnight. A full timestamp such as `2026-11-21T09:00+01:00` also
works.

The two windows differ in length, so compare each finding's share of scanned
tokens and its incidents per 1k tool calls, which the report prints for every
finding, rather than its totals. A short window or a different mix of tasks can
still move these numbers, so treat a change as a signal, not as proof. A long
turn that crosses the date is counted only from the date onward.

## Collecting with hooks

Hook collection records metadata while sessions run, in Git worktrees you opt
in. `ai-install.sh` registers this dotfiles worktree in all four profiles;
other worktrees stay unobserved until you register them with agents closed:

```sh
agent-feedback-install-hooks --repo /absolute/path/to/project
CLAUDE_CONFIG_DIR="$HOME/.claude-work" CODEX_HOME="$HOME/.codex-work" \
  agent-feedback-install-hooks --repo /absolute/path/to/project
```

The installer covers both clients by default; `--agent claude` or
`--agent codex` selects one. It merges into each client's user settings without
changing permissions, trust or disabled-hook settings, and keeps unrelated
handlers. Existing files get private `.agent-feedback-backup-*` copies before
they are replaced atomically. The installer requires strict JSON objects and
refuses duplicate keys, symlinks and hardlinks. It checks both configs first,
but replacement is atomic per file, not across clients, so close config
editors during installation. Reinstalling is idempotent for that worktree.

At run time, a hook's incoming `cwd` must resolve to the registered worktree.
Events from other worktrees are dropped before storage opens.

Each repository is identified by a hash of `origin:` plus its origin URL. A
repository without an origin needs the same `--repository
'owner:canonical-remote'` at installation, analysis and proposal time.
Reinstall after moving the worktree or changing its origin. To stop
collection, remove only the matching `agent-feedback:` handlers. Restoring a
backup instead can overwrite settings changed since.

### Reading collected data

```sh
agent-feedback analyze --repo /absolute/path/to/project
agent-feedback report --format json
agent-feedback propose --repo /absolute/path/to/project --issue ISSUE-0123456789abcdef
```

`analyze` applies the same rules and suggestions as `scan`, limited to one
repository's collected events. `report` summarizes collected sessions: events,
tool failures and known gaps. It never treats an unknown outcome as a failed
task.

`propose` prints a review-only patch that adds recovery guidance to the
repository's root `AGENTS.md` and `CLAUDE.md`. It needs at least three
incidents of a supported rule across two independent sessions. Permission and
collection-health findings never produce a patch. The tool never applies the
patch and never claims an improvement: review it against existing policy and
run the relevant checks yourself.

`ingest --provider PROVIDER --repository ID --mode metadata --source-id EXPORT`
imports immutable hook JSONL from stdin. It accepts hook payloads, not client
stream output.

## Storage and privacy

State lives in `~/.local/state/agent-feedback`: directory mode `0700`, SQLite
database `0600`, seven-day retention and a 16 MiB database quota. SQLite
journals can need extra space. `--state-dir PATH` selects a different private
location. It goes before the subcommand, and must be the same for installation
and inspection.

Prompts, code, commands, output and transcript paths are never stored. Session
IDs and shell-command and file-path fingerprints are kept as hashes, which are
not guaranteed to be anonymous. State is not encrypted.

Live collection fails open: when something goes wrong, the hook prints a fixed
warning and lets the agent continue. Missing telemetry and empty reports
therefore prove neither that the hooks are healthy nor that the work was
correct.

## Limitations

- Every finding carries `task_outcome: unknown`. The tool sees tool calls, not
  whether the task succeeded, so no finding shows that an instruction caused
  waste.
- A file changed by a shell command, rather than an edit tool, still counts as
  re-read.
- Hook compatibility is covered by synthetic tests, not verified live captures.

## Development

```sh
cd llm/agent-feedback
PYTHONPATH=src python3 -m unittest discover -s tests
```

`scan.py` parses transcripts, `hooks.py` normalizes hook payloads into
metadata-only events, `diagnosis.py` holds the rules, `suggest.py` turns
evidence into fixes and `remediation.py` builds `propose` patches.
