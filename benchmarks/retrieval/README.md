# Retrieval skill, Serena, and Context7 token benchmark

The intended comparison uses twelve independent Codex trials: three code questions
with and without Serena, and three Python 3.14 documentation questions with and
without Context7. Both arms receive the same retrieval skill. This measures the
incremental effect of a retrieval tool, not a skill and a tool as interchangeable
products. Each question has one paired comparison, not repeated samples.

`run.py` inherits the configured model and reasoning effort without changing the
user's configuration. It uses an isolated Codex home, an authentication-file
symlink, and a temporary workspace containing three source files. It alternates
pair order, records CLI events and final answers, and reads actual usage from
`turn.completed`. Input already includes cached input; reasoning output is not
added a second time. Total tokens are input plus output. Cached and uncached input
are also reported separately. No monetary cost is estimated.

## Current result: blocked, not a token-saving result

The first attempt on 2026-11-08 could not retrieve evidence. Nested shell calls
failed with `sandbox-exec: sandbox_apply: Operation not permitted`, and the
configured Serena MCP tools were absent from the nested session. Neither answer
explained the requested source behavior. The batch was interrupted after the
first completed pair; a third trial had started but is not included in the results.
No valid paired comparison or twelve-trial result was produced.

[results.json](results.json) retains the two completed failed trials and their
usage, solely as diagnostic evidence. Their token counts must not be compared as
retrieval savings. The temporary artifact directory recorded there holds prompts,
event logs, and session telemetry; the operating system may purge it. Do not commit
or share its `home/auth.json` symlink or authentication material.

The runner now stops after the first trial with no successful retrieval instead
of spending tokens on the rest of a blocked batch. A successful tool call alone
does not establish answer quality: review every answer against its source before
comparing usage. Library resolution, required initialization, retries, and
follow-up requests made inside a trial count toward its actual usage. Preparation
in the parent session, schema discovery here, and the connectivity preflight are
outside the trial totals. Alternating order does not remove cache effects.

## Reproduction

In an environment that permits nested sandboxed Codex execution and exposes the
configured MCP servers:

```sh
python3 -m unittest discover -s benchmarks/retrieval -p test_run.py
python3 benchmarks/retrieval/run.py
```

This starts up to twelve model sessions using the existing configured model and
effort, with a 240-second timeout each. It uses the installed Codex CLI, Serena,
and Context7, without installing dependencies or bypassing the sandbox.
Context7 is instructed to remain anonymous. The documentation baseline fetches
official Python 3.14 sources, while Context7 must resolve and query that version.

A live-tool request-and-result token count is a possible narrower fallback, but
it would exclude model reasoning, repeated context, schemas, and caching. It is
not a substitute for the requested end-to-end consumed-token measurement.
