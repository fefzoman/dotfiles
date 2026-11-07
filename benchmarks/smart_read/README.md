# smart-read and shell retrieval token benchmark

On eight bounded tasks in this repository, lexical smart-read used **9,077 command-and-output tokens**, including a follow-up read for missing source. That was **64.4% less than whole-file reads**, but **87.6% more than targeted shell searches**. The benefit here comes from avoiding whole files; smart-read did not beat careful shell retrieval on token volume.

| Method | Initial output tokens | Commands + output, including required follow-ups | Complete on first read |
|---|---:|---:|---:|
| Whole-file `cat` | 25,433 | 25,496 | 8/8 |
| Targeted `rg -n -C 12`, then `sed` if needed | 2,886 | 4,839 | 3/8 |
| `smart-read search --lexical --path FILE -k 2`, then `sed` if needed | 8,167 | 9,077 | 7/8 |
| Exact `sed` range, location already known | 2,171 | 2,290 | 8/8 |

The exact-range control assumes the answer location is already known. Its 2,290 tokens are a lower-bound comparison, not the cost of discovering those locations. The `rg` baseline uses a fixed twelve-line context around a known function name. When that cuts off the body, the cost includes reading the full function with `sed` as well.

| Task | Whole file | Targeted shell + follow-up | smart-read + follow-up | Known range |
|---|---:|---:|---:|---:|
| Count lines and handle missing files | 919 | 268 | 1,137 | 69 |
| Parse shell file targets | 919 | 517 | 1,138 | 237 |
| Match version mentions | 1,086 | 373 | 1,155 | 77 |
| Discover pinned versions | 1,086 | 691 | 1,157 | 309 |
| Read JSONL tails | 11,687 | 468 | 919 | 162 |
| Configure plugin policy | 5,394 | 1,029 | 1,914 | 639 |
| Install Ponytail | 4,080 | 1,168 | 1,203 | 465 |
| Read a small known skill file | 325 | 325 | 454 | 332 |

All per-task counts include command text and output. The two small Python files each contain two tasks, so their whole-file cost is counted once per independent task; this does not model reuse within one conversation. The small Markdown file uses `cat` as its targeted shell baseline.

The run used repository revision `346ab0d` and the installed `token-count` CLI with `o200k_base`. Installed smart-read matched `llm/smart-read/smart_read.py` byte for byte: SHA-256 `2ba6fa636705cb9b835a0cb261c579f4e0f6afabfa969354c9243eb32bf791d6`. No embeddings were built. Every measured command ran directly with `RTK_DISABLED=1`; RTK did not filter either baseline.

Each initial command ran three times, and its output had to remain identical. Token counts use one copy of that output. Required evidence is the nonblank, noncomment source lines of the target function, or the entire small Markdown file. The runner checks that each line appears in the retrieved text; if any is missing, it adds the exact source range as a follow-up and counts both commands and both outputs. This checks textual coverage, not whether a model would understand the behavior correctly. Smart-read missed eight required lines of `context_efficiency` in its initial result.

Median initial-command latency across the eight per-task medians was 59.1 ms for smart-read, 3.5 ms for targeted shell, and 2.3 ms for whole-file reads. These are local observations with warm caches, not cold-start performance measurements; follow-up time and tokenizer startup are excluded.

These are retrieval-context measurements, not billed model usage. They exclude prompts, reasoning, tool schemas, result envelopes, hook messages, model retries, caching and subsequent conversation turns. Queries contain identifiers and the file path is supplied to both methods. Repository-wide discovery and other repositories were not tested. Smart-read's ranking can change as the repository or installed tool changes.

Reproduce with the existing installed tools:

```bash
python3 benchmarks/smart_read/run.py
```

The runner needs `smart-read`, `rg`, `sed`, `cat` and `token-count` on `PATH`. The tokenizer may download its vocabulary on first use. It writes [results.json](results.json), which includes every command, source hash, range, coverage count, token count and raw-output path. Raw outputs are saved in a temporary directory and may be purged by the operating system. The runner contains assertions for a known tokenizer result, successful commands, stable repeated outputs and complete source coverage after follow-up reads.

For these tasks, use direct reads for small known files and precise shell ranges when the location is known. Smart-read substantially reduces context compared with whole-file reads of large files, and it more often returned a complete function than fixed-context `rg`; that advantage did not translate into fewer tokens than the targeted shell workflow here.
