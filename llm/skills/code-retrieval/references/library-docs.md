# Version-aware library lookup

Use this route only for an unresolved API contract, not routine local navigation. Read the project's lockfile, manifest, or installed metadata to identify the dependency and version. Distinguish the installed version from an explicitly requested upgrade target.

Use the installed Context7 CLI anonymously and noninteractively:

```sh
rtk ctx7 library PACKAGE "VERSION: one unresolved API question" --json
rtk ctx7 docs /RETURNED/LIBRARY/ID "VERSION: the same specific question" --language LANGUAGE --json
```

Select an ID returned by `library`, preferring the official source and an explicitly listed matching version. Never invent a version suffix. If no versioned ID is available, include the target version in the question and verify the returned source URL and content actually cover it. A version in the question alone does not prove a match.

Keep this evidence with the task, not in a new permanent file:

```text
Dependency and target version:
Resolved library ID:
Verified source version and URL:
Relevant contract:
Remaining uncertainty:
```

Reuse the resolution for subsequent questions about that library in the same session. Batch independent reads; do not query again after the contract is settled. Do not use MCP, `ctx7 setup`, `ctx7 login`, saved credentials, or API keys. Continue within anonymous limits without offering sign-in. On a quota/network failure, report it and use the matching official documentation; do not silently substitute memory or another version.

CLI syntax and anonymous support: [official Context7 CLI documentation](https://context7.com/docs/clients/cli). Do not send credentials, private code, or confidential data in queries.
