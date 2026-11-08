# smart-read and shell retrieval token benchmark

The results below preserve the historical eight-task corpus. After Context7's
removal, the current runner excludes its two retired guard fixtures and runs six
tasks. Future aggregate results are not directly comparable to these totals.

On eight bounded tasks in this repository, a shell workflow that discovers function boundaries with `rg` and reads them with `sed` used **4,585 command-and-output tokens**. Lexical smart-read used **9,625**, including boundary discovery and a follow-up read for missing source. The shell workflow used **52.4% fewer tokens than smart-read**. Smart-read used **62.2% fewer tokens than whole-file reads**.

| Method | Initial output tokens | Commands + output, including required follow-ups | Complete on first read |
|---|---:|---:|---:|
| Whole-file `cat` | 25,433 | 25,496 | 8/8 |
| Targeted `rg -n -C 12`, then boundary discovery and `sed` if needed | 2,886 | 6,968 | 3/8 |
| `smart-read search --lexical --path FILE -k 2`, then boundary discovery and `sed` if needed | 8,167 | 9,625 | 7/8 |
| Discover boundaries with `rg`, then read with `sed` | 2,488 | 4,585 | 1/8 |
| Exact `sed` range, location already known | 2,171 | 2,290 | 8/8 |

The discovery workflow starts with the file path and function name, but no line numbers. For Python, it lists top-level function and class definitions, finds the named function, and uses the next definition as its boundary. For the shell fixture, it lists function declarations and closing braces. All discovery commands and their outputs count toward the total. For example:

```bash
rg -n '^(def |class )' llm/read_hint.py
sed -n '21,42p' llm/read_hint.py
```

The runner derives `21,42` from the first command's output. Ground-truth ranges are used only to check coverage and for the explicitly named known-range control. The Markdown task uses `cat` and needs no discovery. The discovery workflow is deliberately two steps, so only that Markdown task is complete after its first command.

The exact-range control assumes the answer location is already known. Its 2,290 tokens are a lower-bound comparison. The fixed-context `rg` and smart-read workflows also pay for boundary discovery whenever their initial output cuts off the required body. Previous results omitted this discovery cost; this run replaces those totals.

| Task | Whole file | Targeted shell + discovery + read | smart-read + discovery + read | Discover + read | Known range |
|---|---:|---:|---:|---:|---:|
| Count lines and handle missing files | 919 | 268 | 1,137 | 126 | 69 |
| Parse shell file targets | 919 | 574 | 1,138 | 294 | 237 |
| Match version mentions | 1,086 | 373 | 1,155 | 193 | 77 |
| Discover pinned versions | 1,086 | 807 | 1,157 | 425 | 309 |
| Read JSONL tails | 11,687 | 1,646 | 919 | 1,340 | 162 |
| Configure plugin policy | 5,394 | 1,577 | 2,462 | 1,187 | 639 |
| Install Ponytail | 4,080 | 1,398 | 1,203 | 695 | 465 |
| Read a small known skill file | 325 | 325 | 454 | 325 | 332 |

All per-task counts include command text and output. The two small Python files each contain two tasks, so their whole-file cost is counted once per independent task; this does not model reuse within one conversation. The small Markdown file uses `cat` as its targeted shell baseline.

The run used repository revision `e2c5039` plus the uncommitted benchmark changes and the installed `token-count` CLI with `o200k_base`. The task source files were unchanged. Installed smart-read matched `llm/smart-read/smart_read.py` byte for byte: SHA-256 `2ba6fa636705cb9b835a0cb261c579f4e0f6afabfa969354c9243eb32bf791d6`. No embeddings were built. Every measured command ran directly with `RTK_DISABLED=1`; RTK did not filter either baseline.

Each initial command ran three times, and its output had to remain identical. Token counts use one copy of that output. Required evidence is the nonblank, noncomment source lines of the target function, or the entire small Markdown file. The runner checks that each line appears in the retrieved text; if any is missing, it discovers the range and reads it with `sed`, counting every command and output. This checks textual coverage, not whether a model would understand the behavior correctly. Smart-read missed eight required lines of `context_efficiency` in its initial result.

Median initial-command latency across the eight per-task medians was 152.9 ms for smart-read, 3.0 ms for targeted shell, 3.0 ms for boundary discovery, and 2.2 ms for whole-file reads. These are local observations with warm caches, not cold-start performance measurements; later discovery steps, follow-up time and tokenizer startup are excluded.

These are retrieval-context measurements, not billed model usage. They exclude prompts, reasoning, tool schemas, result envelopes, hook messages, model retries, caching and subsequent conversation turns. Queries contain identifiers and the file path is supplied to both methods. Repository-wide discovery and other repositories were not tested. Smart-read's ranking can change as the repository or installed tool changes.

Run the current six-task corpus with the existing installed tools, preserving
the historical results file first:

```bash
python3 benchmarks/smart_read/run.py
```

The runner needs `smart-read`, `rg`, `sed`, `cat` and `token-count` on `PATH`. The tokenizer may download its vocabulary on first use. It writes [results.json](results.json), which includes every command, source hash, range, coverage count, token count and initial raw-output path. Discovery and follow-up outputs use the same filename stem with `.discovery.txt` and `.followup.txt` suffixes. Raw outputs are saved in a temporary directory and may be purged by the operating system. The runner contains assertions for Python and shell boundary discovery, a known tokenizer result, successful commands, stable repeated outputs and complete source coverage after follow-up reads.

For these tasks, use direct reads for small known files and discovered shell ranges when the function is known. Smart-read substantially reduces context compared with whole-file reads of large files, and it more often returned a complete function than fixed-context `rg`; that advantage did not translate into fewer tokens than the shell workflows here. Listing every definition also has a cost: on the 965-line JSONL utility, smart-read used 919 tokens while discovery and `sed` used 1,340.
