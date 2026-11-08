# Verified structural file discovery

Use `ast-grep` only for a repeated syntax-based file query whose result is already
verified, not routine text search or speculative pattern learning. If unavailable,
use bounded `rg` plus the installed language parser; do not install it mid-task.

For example, find Python files with a bare exception handler, excluding comments
and strings, without dumping every AST node:

```sh
rtk ast-grep scan --inline-rules '{"id":"bare-except","language":"Python","rule":{"kind":"except_clause","regex":"^except\\s*:"}}' --files-with-matches PATH
```

Keep the scope narrow and queries read-only. Before reusing a new rule, verify
completeness with the project's compatible parser or a focused fixture. Keyword
order, multiline arguments and parser versions can make intuitive patterns miss
matches; syntax matches do not establish symbol identity. Do not emit large JSON
when filenames answer the question. Stop when the result is sufficient.
