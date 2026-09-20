# Coding Agent Efficiency Stack: Ponytail + Serena + Context7 + RTK + Headroom

> Verified against upstream documentation on 2026-09-19. These projects evolve quickly; re-check their current installation commands before automating bootstrap.

## 1. Purpose

These five tools solve different sources of waste in an agentic coding session:

| Tool | Layer | Primary question | Main effect |
|---|---|---|---|
| **Ponytail** | Solution policy | *How much should we build?* | Smaller, simpler implementations; fewer abstractions/dependencies/files |
| **Serena** | Internal code intelligence | *How does this repository work?* | Symbol-level retrieval, reference tracing, semantic editing |
| **Context7** | External dependency knowledge | *How does this library/API work in the relevant version?* | Retrieves current library/API docs and examples |
| **RTK** | Shell execution | *How much terminal output does the model need?* | Rewrites supported shell commands to compact equivalents |
| **Headroom** | LLM transport/context | *How much accumulated context must reach the model?* | Local compression, cache-aware context management, reversible retrieval |

The stack is useful because the tools operate at different stages. Their savings overlap, so percentages must **not** be added together.

This repository installs the stack for personal and work profiles of both
Codex and Claude Code. Serena and Context7 are user-level MCP servers,
Ponytail is a native plugin, RTK uses Codex instructions or Claude hooks, and
Headroom wraps each CLI. The Codex token profiler remains Codex-specific.

---

## 2. Mental model

```text
                    Project instructions
                 + Ponytail solution policy
                           │
                           ▼
                    ┌─────────────┐
                    │Codex/Claude │
                    │ reasoning   │
                    └──────┬──────┘
                           │ chooses what it needs
        ┌──────────────────┬──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│    Serena    │   │   Context7   │   │     Bash     │
│ internal code│   │ external docs│   └──────┬───────┘
│ navigation   │   │ and APIs     │          │
└──────┬───────┘   └──────┬───────┘          ▼
       │                  │            ┌──────────────┐
       │                  │            │     RTK      │
       │                  │            │ rewrite/filter
       │                  │            └──────┬───────┘
       └──────────┬───────┴───────────────┬──┘
                  │                       │
                  └───────────┬───────────┘
                          │ tool results
                          ▼
                   next model request
                          │
                          ▼
                  ┌───────────────┐
                  │   Headroom    │
                  │ local proxy   │
                  │ compression   │
                  └───────┬───────┘
                          │
                          ▼
                         LLM
```

This diagram is conceptual. Headroom sits on the model transport path, so it operates on each request that flows through its proxy. Ponytail is not a transport component: it changes the agent's implementation decisions throughout the task.

---

## 3. Ponytail

### What it does

Ponytail is an implementation-policy skill/plugin. Its core rule is to stop at the earliest solution that satisfies the task:

1. Does this need to exist at all?
2. Does it already exist in the codebase?
3. Can the standard library do it?
4. Can the native platform do it?
5. Can an already-installed dependency do it?
6. Can it be one line?
7. Only then write the minimum new code that works.

It explicitly says minimalism comes **after understanding the real flow**. It also protects validation at trust boundaries, data-loss prevention, security, accessibility, and explicitly requested requirements.

### Codex integration

Current upstream Codex plugin installation:

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

The plugin provides skills and lifecycle hooks. In Codex, skills can be invoked with `@`, for example:

```text
@ponytail
@ponytail-review
```

A root `AGENTS.md` can also carry the same core policy, which is useful for hosts where the full plugin is not active.

### Claude Code integration

```bash
claude plugin marketplace add DietrichGebert/ponytail
claude plugin install ponytail@ponytail
```

Claude exposes the corresponding `/ponytail` commands. This repository runs
those commands once for `~/.claude` and once with
`CLAUDE_CONFIG_DIR=~/.claude-work`.

### Impact

Ponytail primarily reduces:

- generated LOC;
- new abstractions;
- unnecessary dependencies;
- files changed;
- code that later has to be read, tested, diffed, reviewed, and sent back through the model context.

The Ponytail project's current benchmark reports, for its specific benchmark setup, approximately:

- 54% less LOC;
- 22% fewer tokens;
- 20% lower cost;
- 27% lower elapsed time.

Treat these as **project-reported benchmark results, not expected universal savings**. The project itself notes that token savings are a side effect and can vary by model and task.

### Main risk

Over-minimization can be harmful if the agent skips understanding, validation, security, or required edge cases. The Ponytail rules explicitly guard against this.

---

## 4. Serena

### What it does

Serena is a semantic code-intelligence MCP server. It exposes IDE-like operations at the symbol level using language-server information.

Typical high-value operations include:

```text
get_symbols_overview
find_symbol
find_referencing_symbols
replace_symbol_body
```

The goal is to avoid this pattern:

```text
grep huge repository
→ read several whole files
→ manually infer symbol relationships
```

and instead do:

```text
find relevant symbol
→ inspect its structure
→ trace references/callers
→ read only the bodies needed
→ edit at the symbol boundary when appropriate
```

### Codex integration

Current upstream shortcut:

```bash
serena setup codex
```

Equivalent Codex MCP configuration is currently documented as:

```toml
[mcp_servers.serena]
startup_timeout_sec = 15
command = "serena"
args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]
```

Verification:

```text
/mcp
```

For Codex App sessions that do not start in the project directory, Serena recommends activating the project at session start:

```text
Activate the current dir as project using serena.
```

Serena also documents Codex lifecycle hooks that remind the agent to prefer symbolic retrieval when it drifts into repeated grep/full-file reads.

### Preferred retrieval pattern

Use this sequence when working with normal source code:

```text
1. activate project if necessary
2. get symbol/file overview
3. find target symbol
4. find references/callers when behavior can affect siblings
5. fetch bodies only when needed
6. make the smallest correct edit
```

Use raw filesystem/search tools when they are more appropriate, for example:

- non-code files;
- generated artifacts;
- exact text searches;
- unsupported language-server cases;
- very small known files where semantic lookup adds no value.

### Impact

Serena mainly lowers:

- full-file reads;
- broad grep output;
- context spent discovering code structure;
- accidental edits in the wrong layer;
- time spent finding callers and related symbols.

Its value grows with repository size and symbol/reference complexity.

### Main costs

- language-server startup/indexing;
- extra MCP process/state;
- language-specific LSP limitations;
- possible duplication if more than one Serena instance is configured.

---

## 5. Context7

### What it does

Context7 provides current documentation and examples for third-party libraries and APIs. Its role is external knowledge, not repository navigation.

The key distinction is:

```text
Serena   → "How does OUR code work?"
Context7 → "How does THIS dependency/API work?"
```

For example:

```text
Where is our FastAPI app initialized?
    → Serena

How does StreamingResponse behave in the current FastAPI version?
    → Context7
```

### Codex integration

Current upstream options include:

```bash
npx ctx7 setup --codex
```

or Codex plugin installation:

```bash
codex plugin marketplace add upstash/context7
codex plugin add context7@context7-marketplace
```

Use whichever installation path matches the host/bootstrap strategy. The project `AGENTS.md` should only describe **when to use Context7**, not require one particular bootstrap mechanism.

### Preferred usage pattern

Use Context7 when implementation depends on:

- third-party library APIs;
- version-specific behavior;
- recently changed frameworks;
- SDK/provider configuration;
- unfamiliar dependencies already present in the repository.

Do **not** query Context7 automatically on every coding task.

A useful decision rule is:

```text
Need information?

About this repository?
    → Serena

About an external library/API?
    → Context7

Stable language/runtime behavior already known?
    → use neither
```

### Interaction with Ponytail

Ponytail asks whether an already-installed dependency already solves the problem.

Context7 can answer that efficiently:

```text
Ponytail:
"Can an installed dependency already do this?"

        ↓

Context7:
"Yes — use library X's existing API."

        ↓

Codex:
reuse the dependency instead of building a new abstraction
```

This can reduce both generated code and unnecessary dependency additions.

### Interaction with Serena

Serena and Context7 are complementary:

```text
                   Codex
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
       Serena                Context7
   internal project       external dependency
      knowledge               knowledge
```

A typical task may legitimately need both:

```text
1. Serena finds where the project uses SQLAlchemy.
2. Context7 retrieves the relevant SQLAlchemy API behavior.
3. Codex applies that API to the existing project pattern.
```

### Interaction with Headroom

Context7 introduces additional documentation snippets into context.

Headroom can compress/deduplicate those snippets on subsequent model requests, but this does **not** justify querying Context7 broadly. Prefer targeted retrieval first, then let Headroom optimize what remains.

### Impact

Context7 primarily reduces:

- stale API assumptions;
- hallucinated library methods/options;
- unnecessary web searches;
- custom code written because Codex did not know an installed library already supports the requirement;
- rework caused by version mismatch.

### Main cost

External documentation is itself context. Unnecessary Context7 calls can increase token consumption.

Use it conditionally, not reflexively.


## 6. RTK

### What it does

RTK is a CLI proxy/filter for common developer commands. It reduces the terminal output an agent has to ingest.

Conceptually:

```text
Codex wants:
    cargo test

Codex PreToolUse hook:
    rtk rewrite "cargo test"

Executed command:
    rtk cargo test

Result:
    compact, task-relevant output
```

This is different from Headroom: RTK reduces the **source shell output before it becomes model context**.

### Codex integration

RTK now documents a native Codex `PreToolUse` hook:

```bash
rtk init --codex
```

Project-scoped setup currently creates/updates:

```text
.codex/hooks.json
AGENTS.md
```

Global setup:

```bash
rtk init --global --codex
```

After setup, restart Codex and trust project hooks when prompted.

Current RTK documentation says the native Codex hook transparently rewrites supported `Bash` commands. Therefore, Codex generally should **not manually add `rtk` to every command** when the hook is healthy.

To force raw execution for a particular command:

```bash
RTK_DISABLED=1 <command>
```

Example:

```bash
RTK_DISABLED=1 git diff
```

### Impact

RTK's project documentation advertises up to roughly 90% fewer Bash-output bytes for supported workflows. That figure applies to tool output, **not necessarily total session tokens**.

RTK is especially useful for:

- test suites;
- build output;
- git output;
- package-manager output;
- repetitive command results.

### Main risk

Filtering can omit details needed for unusual debugging. The escape hatch is simple: rerun the specific command with RTK disabled or narrow the raw command manually.

---

## 7. Headroom

### What it does

Headroom is a local context-compression layer. For Codex CLI, the normal entry point is:

```bash
headroom wrap codex
```

The wrapper starts/reuses a local proxy and routes Codex model traffic through it.

Headroom's current default context posture is cache-oriented: it tries to preserve stable previous turns for provider prefix-cache efficiency while compressing the live part of the context.

It operates on content such as:

- tool results;
- logs;
- files;
- structured data;
- retrieved chunks;
- conversation history.

Headroom also provides reversible compression/retrieval mechanisms so the original can be recovered when needed.

### Serena relationship

This is important: current Headroom `wrap` behavior registers **Serena as its default code-memory MCP** for semantic, symbol-level navigation.

To disable that registration:

```bash
headroom wrap codex --code-memory none
```

Therefore, do **not** independently configure another Serena instance unless you deliberately disable Headroom's Serena management.

### Impact

Headroom primarily reduces:

- accumulated input tokens reaching the model;
- repeated/stale context;
- large tool outputs that still remain after upstream filtering.

The Headroom project currently advertises large token savings in its examples/documentation, but actual results depend heavily on content type. Repetitive logs/JSON generally compress much better than already-concise source code.

### Main costs

- local proxy process;
- some compression latency;
- debugging complexity if you forget traffic is passing through a proxy;
- diminishing returns when Serena and RTK have already removed most waste.

---

## 8. How the five tools reinforce each other

A useful way to think about the stack is **waste prevention as early as possible**:

```text
Ponytail
    ↓
avoid unnecessary implementation work

Serena
    ↓
avoid unnecessary repository reads/searches

Context7
    ↓
avoid stale or guessed dependency/API knowledge

RTK
    ↓
avoid unnecessary shell-output volume

Headroom
    ↓
compress remaining context before the model sees it
```

Earlier reductions are usually preferable because they prevent downstream work entirely.

### Example: bug fix

Task:

```text
Deleted users still appear in /users.
```

Without the stack, an agent may:

1. grep broadly;
2. read multiple complete files;
3. patch only the route mentioned by the ticket;
4. run a noisy full test suite;
5. send large logs and diffs through several model turns.

With the stack:

1. **Ponytail** says: find the root cause and fix it once, in the shared path.
2. **Serena** finds the endpoint, shared service/repository symbol, and all callers.
3. If the fix depends on third-party behavior, **Context7** retrieves the relevant current API/docs.
4. Codex reads only the required symbol bodies and external documentation.
5. Codex makes the smallest root-cause diff.
6. **RTK** compacts test/git output.
7. **Headroom** compresses the remaining accumulated context for the next model call.
8. **Ponytail review** can check the diff for accidental abstractions or unnecessary files.

---

## 9. Configuration ownership: avoid duplicate machinery

### Serena: choose exactly one owner

#### Option A — Headroom owns Serena

Use:

```bash
headroom wrap codex
```

Do not separately register another Serena MCP server.

This is the simplest Codex CLI path if Headroom is always your launcher.

#### Option B — Serena owns itself

Configure Serena directly:

```bash
serena setup codex
```

Then launch Codex through Headroom without Headroom-managed code memory:

```bash
headroom wrap codex --code-memory none
```

This is useful when you want Serena configured independently of Headroom.

### Do not run two Serena servers for the same project

Two Serena instances can cause:

- duplicate tools;
- duplicate indexing/LSP processes;
- more memory;
- confusing project activation/state;
- uncertain tool selection by the agent.

---

## 10. Hook coexistence

RTK, Serena, and Ponytail can all use Codex lifecycle hooks.

Their responsibilities are distinct:

```text
RTK       → PreToolUse Bash command rewriting
Serena    → activation/reminders/reset/cleanup
Ponytail  → session activation, mode tracking, subagent rules
```

Do not replace an existing hook file blindly. Merge hook entries when manual configuration is necessary.

In particular:

- `rtk init --codex` may manage `.codex/hooks.json` and an RTK section in `AGENTS.md`;
- Serena documents user-level Codex hooks in `~/.codex/hooks.json`;
- Ponytail's Codex plugin carries its own lifecycle-hook definition.

After installation, inspect Codex's hook view and verify all expected hooks are trusted and active.

---

## 11. `AGENTS.md` relationship

The project-root `AGENTS.md` should describe **behavior**, not reproduce installation manuals.

It should tell Codex:

- prefer Serena for semantic code exploration;
- use Context7 conditionally for third-party library/API knowledge;
- let RTK's hook handle supported shell commands;
- apply Ponytail's minimum-correct-solution discipline;
- treat Headroom as transparent and never depend on compression for correctness;
- minimize context before Headroom, rather than generating noise because “it will be compressed anyway.”

This repository's companion `AGENTS.md` is intentionally short because every always-on instruction consumes context.

If an installer adds a managed RTK block to `AGENTS.md`, preserve it or reconcile it with the equivalent rules rather than deleting it blindly.

---

## 12. Recommended task workflow

```text
1. Understand the request.
2. Activate/check Serena when semantic code work is needed.
3. Locate symbols and references semantically.
4. If implementation depends on third-party behavior, query Context7 narrowly for the relevant library/API.
5. Apply Ponytail's ladder to choose the smallest correct solution.
6. Edit the fewest files necessary.
7. Run the narrowest useful validation.
8. Let RTK compact supported terminal output.
9. Inspect the final diff.
10. Use @ponytail-review for non-trivial changes when available.
11. Let Headroom optimize transport/context automatically.
```

The ordering matters: do not use Headroom as an excuse for broad reads or huge commands. Prevent waste upstream first.

---

## 13. When to bypass a layer

| Situation | Action |
|---|---|
| Serena cannot understand a file/language | Use Codex filesystem/search tools narrowly |
| External dependency docs are unnecessary/stable | Skip Context7 |
| Context7 lacks the needed library/version | Use authoritative upstream docs or inspect the installed package narrowly |
| Exact raw command output is required | `RTK_DISABLED=1 <command>` |
| Suspect compression hid a necessary detail | Retrieve the original if Headroom retrieval is available, or rerun a narrow raw read/command |
| User explicitly requests an abstraction/dependency/design | Ponytail should follow the explicit requirement |
| Security, trust-boundary validation, accessibility, data-loss protection | Never simplify these away |
| Tool unavailable/broken | Continue with built-in Codex capabilities; correctness must not depend on the optimization stack |

---

## 14. Expected impact by dimension

| Dimension | Ponytail | Serena | Context7 | RTK | Headroom |
|---|---:|---:|---:|---:|---:|
| Generated LOC | High | Low | Medium | None | Low |
| Files/dependencies added | High | Low | Medium | None | None |
| Code-reading tokens | Indirect | High | Low | Low | Medium/High |
| External-doc tokens | None | None | High/targeted | None | Medium |
| Shell-output tokens | Indirect | Low | None | High | Medium |
| Conversation/context tokens | Indirect | Medium | Medium | Medium | High |
| Repository understanding | Medium | High | None | None | Low |
| Dependency/API accuracy | Medium | Low | High | None | Low |
| Runtime overhead | Very low | Index/LSP cost | Retrieval/network cost | Very low | Proxy/compression cost |
| Main failure mode | Underbuilding | LSP/tool mismatch | Unnecessary/stale retrieval | Hidden raw detail | Over-compression / proxy debugging |

The tools are complementary, but their gains are **not additive**. For example, if RTK reduces a 10,000-line test log to a small failure summary, Headroom has much less left to compress.

---

## 15. What to measure

If the goal is to prove whether this stack is worthwhile, track per task:

- total model input/output tokens;
- Headroom tokens saved/compression ratio;
- raw vs RTK shell-output bytes;
- number of full-file reads;
- number of Serena symbolic retrievals;
- number of Context7 lookups and whether they changed implementation decisions;
- generated diff LOC;
- number of files changed;
- dependencies added;
- task latency;
- test pass/fail;
- number of reruns caused by missing context.

The important metric is not maximum compression. It is **correct work per token and per unit time**.

---

## 16. Upstream references

### Ponytail

- https://github.com/DietrichGebert/ponytail
- https://github.com/DietrichGebert/ponytail/blob/main/AGENTS.md
- https://github.com/DietrichGebert/ponytail/blob/main/.codex-plugin/plugin.json
- https://github.com/DietrichGebert/ponytail/blob/main/hooks/claude-codex-hooks.json

### Serena

- https://github.com/oraios/serena
- https://github.com/oraios/serena/blob/main/docs/02-usage/030_clients.md
- https://github.com/oraios/serena/blob/main/docs/02-usage/050_configuration.md
- https://github.com/oraios/serena/blob/main/src/serena/tools/symbol_tools.py

### Context7

- https://github.com/upstash/context7
- https://github.com/upstash/context7/blob/master/docs/clients/codex.mdx

### RTK

- https://github.com/rtk-ai/rtk
- https://github.com/rtk-ai/rtk/blob/develop/docs/guide/getting-started/supported-agents.md

### Headroom

- https://github.com/headroomlabs-ai/headroom
- https://github.com/headroomlabs-ai/headroom/blob/main/docs/content/docs/proxy.mdx
- https://github.com/headroomlabs-ai/headroom/blob/main/docs/content/docs/mcp.mdx
