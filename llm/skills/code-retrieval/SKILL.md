---
name: code-retrieval
description: Apply automatically before searching repository code or reading part of a large file; choose rg plus sed or smart-read from what is already known.
---

# Choose the next read

Start with what the task already gives you: a path, an identifier, an exact string, or only a description of behavior. Use the smallest read that can answer the unresolved question. Reuse earlier results and ranges after interruptions.

| What you know | First action |
|---|---|
| A small named file | Read it directly. |
| A path and useful line range | Read that range with `sed -n 'START,ENDp' FILE`. |
| An identifier or exact string | Use bounded `rg -n` searches, then read the enclosing definition with `sed`. |
| A filename or extension, but no path | Locate candidates with `rg --files` and a glob, then search those files. |
| Behavior, but no useful identifier | Try `smart-read search "<behavior>" --lexical --path PATH` in the target repository; omit the path only when unknown. |
| A known large file whose structure is hard to locate with text search | Use `smart-read outline FILE`, then read the relevant ranges. |

Prefix shell commands with RTK as required by the agent policy. Bound searches by the narrowest plausible path and result count; expand only when the first scope leaves a specific question unanswered. For symbol relationships or nested definitions that text boundaries cannot establish safely, use the existing Serena session when available.

## Discover ranges before reading

For a known identifier, locate its definition and neighboring boundaries with `rg -n`. Read from the definition through its complete body, including decorators, relevant validation and error handling. A neighboring match is a boundary only when its scope proves it: the next top-level definition can bound a top-level Python function, but nested methods and multiline shell bodies need structural inspection. Use an outline or symbol lookup when the end is unclear.

Check whether the retrieved context answers the question. Search snippets can omit branches or callers; follow up with the missing range or references. If a smart-read result is incomplete, use `rg` and `sed` to fill the gap. If exact searches repeatedly fail to locate the behavior, switch to a behavior query rather than repeating equivalent searches. If smart-read is unavailable or cannot handle the content, continue with bounded shell reads.

## Keep the evidence in scope

The eight-task benchmark in this repository started with known file paths. Including range discovery and follow-up reads, `rg` plus `sed` used 4,585 retrieval tokens versus smart-read's 9,625. This supports shell retrieval for those tasks; it does not establish a winner for repository-wide behavior discovery. The behavior-query choice above is a heuristic, not a measured advantage.

Do not run `smart-read index` or create embeddings unless explicitly requested. Stop retrieving when the requested behavior is explained or the change has enough context to trace its affected callers and checks.
