# smart-read

Hybrid code search for Claude Code and Codex. It returns the few line ranges a task needs instead of whole files, so
less code enters, and is then re-read from, the conversation context.

```bash
smart-read search "where are spend API retries configured"     # whole repo
smart-read search "token refresh" --path src/auth/ -k 3          # file, directory prefix or glob
smart-read search "facebook_spend" --lexical                     # no models: BM25 + trigram only
smart-read outline models/marts/ad_spend_daily.sql               # symbols with line ranges, no models
smart-read index                                                 # embed every chunk now
```

## How it works

1. **Chunks follow symbols.**
   - Python uses `ast`: each function or class is one chunk, and large classes split into their methods.
   - SQL/Jinja, Terraform, YAML, Markdown and C-like languages split where a definition starts.
   - Chunks are merged up to about 60 lines; longer ones split into overlapping 60-line windows.
   - Files come from `git ls-files` (tracked and untracked, honoring ignores); binary files and files over 512 KB are skipped.
2. **Three rankings are fused** with Reciprocal Rank Fusion (k = 60):
   - **BM25** over SQLite FTS5 with Porter stemming. camelCase and snake_case identifiers are split, and symbol and path are weighted 5 and 2.
   - **Trigram** FTS5, for partial identifiers and paths.
   - **Dense cosine** over local ONNX embeddings, computed exactly by brute force.
3. **Fusion is weighted** BM25 0.7 / trigram 0.3 / dense 1. The top `k` are printed with line numbers, capped at 9,000
   characters.

The index is one SQLite file per repository under `~/.cache/smart-read`; models live in `~/.cache/smart-read/models` (fastembed defaults to `$TMPDIR`, which macOS purges). Each query re-chunks only files whose mtime or
size changed. When more than 200 chunks lack embeddings, the query starts `smart-read index` in the background and
answers lexically until it finishes. Changing the embedding model re-embeds everything.

Models (fastembed, CPU) can be overridden with `SMART_READ_EMBED`; the default was chosen by
the evaluation below.

## Evaluation

Run `python eval.py` against your own repositories to reproduce it. It uses the CodeSearchNet protocol on this
machine's repositories: Python docstrings are stripped from the indexed copy, each docstring's first sentence is the
query, and the target is the chunk holding that function.

672 queries over 952 chunks from four repositories on this machine, measured on 10 CPU threads. The default is the
weighted hybrid (bold).

| Method | MRR@10 | R@1 | R@5 | ms/query |
|---|---:|---:|---:|---:|
| BM25 | 0.443 | 0.314 | 0.625 | 1 |
| BM25 + trigram | 0.437 | 0.311 | 0.622 | 2 |
| dense `jina-embeddings-v2-base-code` | 0.537 | 0.414 | 0.696 | 17 |
| **hybrid, weighted RRF 0.7 / 0.3 / 1** | **0.554** | **0.418** | **0.754** | 17 |

Model selection, with equal-weight fusion:

| Embedding | dense MRR@10 | hybrid MRR@10 | hybrid R@5 | indexing speed |
|---|---:|---:|---:|---:|
| `snowflake-arctic-embed-xs` | 0.328 | 0.486 | 0.665 | 37 chunks/s |
| `bge-small-en-v1.5` | 0.483 | 0.504 | 0.695 | 13 chunks/s |
| `jina-embeddings-v2-base-code` | 0.537 | 0.534 | 0.722 | 6 chunks/s |

- **Fusion weights:** weighting BM25, trigram and dense 0.7 / 0.3 / 1 raised the hybrid from 0.534 to 0.554 MRR@10.
- **No reranking.** Every CPU cross-encoder fastembed offers lowered the hybrid's MRR@10 (0.509–0.532) and added 0.7–4.8 s per query.
- **Caveat:** docstring queries are a proxy. Agent queries mixing identifiers with prose should favor the lexical and trigram lists more.

## Agent integration

- The global agent policies tell both agents to use `smart-read` to find code by behavior or to read part of a large file.
- `read_hint.py`, a PreToolUse hook for Claude Read/Bash and Codex Bash, adds a non-blocking note when the agent reads a
  file of 80 or more lines whole with `cat` or an unranged Read. Set `READ_HINT_MIN_LINES` to change the threshold.
