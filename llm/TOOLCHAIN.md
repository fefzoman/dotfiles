# Coding Agent Toolchain: Delivery and Efficiency

## 1. Purpose

| Tool | Layer | Question | Effect |
|---|---|---|---|
| **Ponytail** | Solution policy | How much should we build? | Smaller implementations; fewer abstractions/dependencies/files |
| **Serena** | Internal code intelligence | How does this repo work? | Symbol-level retrieval, reference tracing, semantic editing |
| **Context7** | External dependency knowledge | How does this library/API work in this version? | Current library/API docs and examples |
| **RTK** | Shell execution | How much terminal output does the model need? | Rewrites supported commands to compact equivalents |
| **Headroom** | LLM transport/context | How much accumulated context must reach the model? | Local compression, cache-aware context management, reversible retrieval |
| **Spec Kit** | Feature delivery | What should this feature do, and what remains? | Project-local specification, plan, and task ledger |
| **Superpowers** | Implementation discipline | How do we implement and verify the change? | Conditional TDD, debugging, verification, and review skills |

The tools act at different stages; their savings overlap, so percentages are **never added**.

This repo installs the stack for personal and work profiles of Codex and Claude Code: Serena and Context7 as user-level MCP servers, Ponytail as a native plugin, RTK via Codex and Claude hooks, Headroom as a shared local proxy that every profile reaches through its config (§7). `token-profiler` reads local Codex and Claude sessions per profile.

Two local safeguards complement them, neither runs `/compact` automatically:

- Codex: a hook warning when a large same-thread context nears a quota stop;
- Claude Code: the same warning in its native, token-free status line, which also shows prompt-cache state.

## 2. Mental model

```text
project instructions + Ponytail policy → Codex/Claude reasoning
  → chooses: Serena (internal code) | Context7 (external docs) | Bash → RTK (rewrite/filter)
  → tool results → next model request → Headroom (local proxy compression) → LLM
```

Conceptual only. Headroom sits on the transport path and processes every request through its proxy. Ponytail is not transport: it shapes implementation decisions throughout the task.

## 3. Ponytail

Implementation-policy plugin: stop at the earliest rung that works — (1) needed at all? (2) already in the codebase? (3) stdlib? (4) native platform? (5) installed dependency? (6) one line? (7) minimum new code. Minimalism comes **after understanding the real flow**; trust-boundary validation, data-loss prevention, security, accessibility and explicit requirements are never cut.

```bash
codex plugin marketplace add DietrichGebert/ponytail && codex plugin add ponytail@ponytail
claude plugin marketplace add DietrichGebert/ponytail && claude plugin install ponytail@ponytail
```

- Codex: skills + lifecycle hooks; invoke with `@ponytail`, `@ponytail-review`. A root `AGENTS.md` can carry the core policy where the plugin isn't active.
- Claude: `/ponytail` commands. This repo installs once for `~/.claude` and once with `CLAUDE_CONFIG_DIR=~/.claude-work`.

**Reduces:** generated LOC, new abstractions, unnecessary dependencies, files changed, and code later read/tested/diffed/reviewed/sent back through context. The project's own benchmark reports ~54% less LOC, 22% fewer tokens, 20% lower cost, 27% less elapsed time — project-reported, not universal; token savings are a side effect and vary by model and task.

**Risk:** over-minimization that skips understanding, validation, security or required edge cases (the rules guard against this).

## 4. Serena

Semantic code-intelligence MCP server exposing IDE-like, language-server-backed symbol operations: `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`, `replace_symbol_body`. It replaces *grep huge repo → read whole files → infer relationships* with *find symbol → inspect structure → trace references → read only needed bodies → edit at the symbol boundary*.

Setup (`configure_agent_mcps` in `llm/ai-install.sh`, all four profiles):

```bash
codex mcp add serena -- serena start-mcp-server --context=codex --project-from-cwd --open-web-dashboard false
claude mcp add --scope user serena -- serena start-mcp-server --context=claude-code --project-from-cwd --open-web-dashboard false
```

Upstream's `serena setup codex` writes the equivalent Codex entry. Verify with `/mcp`. Codex App sessions not started in the project dir: say "Activate the current dir as project using serena." Serena also documents Codex lifecycle hooks that nudge the agent back to symbolic retrieval when it drifts into repeated grep/full-file reads.

**Retrieval order:** activate project if needed → overview → target symbol → references/callers when siblings may be affected → bodies only when needed → smallest correct edit. Use raw file/search tools for non-code files, generated artifacts, exact-text search, unsupported languages, and tiny known files.

**Reduces:** full-file reads, broad grep output, context spent discovering structure, edits in the wrong layer, time finding callers. Value grows with repo size and reference complexity.

**Costs:** LSP startup/indexing, extra MCP process/state, per-language LSP limits, duplication if more than one Serena instance is configured.

## 5. Context7

Current docs/examples for third-party libraries and APIs — external knowledge, not repo navigation. Serena: "how does OUR code work?" (where is our FastAPI app initialized?). Context7: "how does THIS dependency work?" (how does `StreamingResponse` behave in the current FastAPI?).

Install via `npx ctx7 setup --codex`, or `codex plugin marketplace add upstash/context7 && codex plugin add context7@context7-marketplace`. `AGENTS.md` should say only *when* to use it, not how to bootstrap it.

**Use when** the work depends on third-party APIs, version-specific behavior, recently changed frameworks, SDK/provider config, or unfamiliar dependencies already in the repo. Not on every task.

**Version guard:** in Claude Code and Codex, `llm/context7_version_guard.py` (`PreToolUse`) denies `query-docs` when the project's `.venv`, `venv`, `uv.lock`, `poetry.lock`, `requirements*.txt` or `node_modules` pins the library and neither `libraryId` nor the query names that version.

**Decision rule:** about this repo → Serena; about an external library/API → Context7; stable, known language/runtime behavior → neither.

**Interactions:**
- Ponytail asks "can an installed dependency do this?"; Context7 answers "yes, use library X's API", so the agent reuses it instead of building or adding something.
- With Serena, e.g.: Serena finds where the project uses SQLAlchemy → Context7 gets the relevant API behavior → agent applies it to the existing pattern.
- Headroom can compress/dedupe Context7 snippets on later requests, but that doesn't justify broad queries; retrieve narrowly first.

**Reduces:** stale API assumptions, hallucinated methods/options, unnecessary web searches, custom code for features an installed library already has, version-mismatch rework. **Cost:** docs are context; use conditionally, not reflexively.

## 6. RTK

CLI proxy/filter that shrinks shell output **before it becomes model context** (Headroom compresses after). Example: Codex wants `cargo test` → `PreToolUse` hook runs the RTK processor → executes `rtk cargo test` → compact, task-relevant output.

Verified with **Codex CLI 0.162.1 and RTK 0.49.0**: Codex supports `PreToolUse` rewrites for shell and unified-exec calls, matched as `Bash` with `tool_input.command`. RTK's `init --codex` installs `AGENTS.md`/`RTK.md` instructions only; it does not install a Codex hook. This repo's installer separately merges a Bash hook into both Codex profiles and installs `codex_rtk_hook.py`. The adapter uses `rtk hook claude` and adds the `permissionDecision: "allow"` field required by [Codex's hook contract](https://learn.chatgpt.com/docs/hooks#pretooluse). It changes the command, while Codex's normal permission and sandbox checks still apply.

After installation, restart the shell. The `codex` function passes `--dangerously-bypass-hook-trust` for personal and work CLI sessions, including new or changed hooks. Sessions launched outside this shell function still require review in `/hooks`. Confirm a plain `git status` tool call executes as `rtk git status` before relying on automatic rewriting. Until then, manually prefix supported commands. `smoke-test.sh` checks configuration and the installed RTK processor's output contract, but cannot establish runtime trust. Force raw output with `RTK_DISABLED=1 <command>` (e.g. `RTK_DISABLED=1 git diff`); already-prefixed and unsupported commands pass through unchanged.

**Impact:** advertised up to ~90% fewer Bash-output bytes for supported workflows — tool output, not total session tokens. Best on tests, builds, git, package managers, repetitive output. **Risk:** filtering can hide details for unusual debugging; rerun that command raw or narrow it.

## 7. Headroom

Local context-compression layer. This repo runs it as a persistent, supervised proxy and routes every profile to it via config, keeping Serena under the repo's direct configuration:

```bash
headroom install apply --preset persistent-service --scope provider \
  --providers manual --target claude --target codex --env HEADROOM_DEDUPE=0
```

This installs the `com.headroom.default` launchd service on `127.0.0.1:8787` and writes `env.ANTHROPIC_BASE_URL` into `~/.claude/settings.json` and a `model_provider = "headroom"` block into `~/.codex/config.toml`. `install apply` covers only those two; `agent_config.py headroom-work` applies the same entries to `~/.claude-work` and `~/.codex-work` using Headroom's own installer modules. Config routing is used instead of `headroom wrap` because IDE extensions (Claude Code, Codex in VS Code) launch their own binaries without a shell wrapper, and `wrap codex` rewrites `config.toml` itself, fighting the persistent block. `HEADROOM_DEDUPE=0` because dedup edits replay from a 10-minute tracker, so idle gaps under the 1-hour prompt cache would still miss it.

The Codex block gets `requires_openai_auth = true` only when that profile is logged in with ChatGPT at install time. After a later ChatGPT login (e.g. `codex-work`, currently logged out), rerun the installer, or requests fail with 401 "Missing bearer".

Default posture is cache-oriented: keep stable earlier turns intact for provider prefix caching, compress the live part. It acts on tool results, logs, files, structured data, retrieved chunks and history, with reversible compression/retrieval to recover originals.

**MCP:** config routing registers no MCP servers; Serena is owned by the installer (§9). On Claude, the proxy itself injects and resolves `headroom_retrieve`, so no `headroom mcp serve` server is needed.

**Reduces:** accumulated input tokens, repeated/stale context, large tool outputs left after upstream filtering. Advertised savings depend on content: repetitive logs/JSON compress far better than concise source. **Costs:** local proxy process, compression latency, debugging confusion when you forget the proxy, diminishing returns after Serena and RTK.

### Transport-specific behavior

Don't assume a Headroom feature applies to every protocol; check the actual request handler first. In installed `0.40.0` (re-checked in source on 2026-10-10):

- Codex uses the OpenAI Responses API over WebSocket. `response.create` frames are compressed, but `HEADROOM_COLD_RECOMPACT` and `HEADROOM_CACHE_TTL_LEARN` aren't wired into that handler — enabling them for Codex is a placebo.
- Claude Code uses Anthropic `/v1/messages`, whose handler does have cold-prefix recompaction and cache observation. Neither is enabled: TTL learning only records observations until an offline estimator builds a learned table, and the reused proxy is shared, not scoped to one Claude profile.

Normal compression stays on for both; still minimize context before it reaches Headroom.

### Same-thread compaction safeguards

Goal: cut the first fresh-token spike after a long quota-reset pause without switching threads, handing off, or giving up warm cache early.

| Agent | Signals | Mechanism | Result |
|---|---|---|---|
| Codex | Rollout `token_count`: input context, active primary/secondary quota windows | `UserPromptSubmit` hook; warns once while the condition holds | Recommend `/compact`, resume same thread |
| Claude Code | Status-line JSON: context tokens/%, 5-hour and 7-day usage, cache warmth | Token-free persistent status line | Recommend `/compact`, continue same conversation |

Threshold: context ≥ 120,000 input tokens **and** either active quota window ≥ 85% used. Code: `llm/codex/codex_compact_warning.py`, `llm/codex/codex-hooks.json`, `llm/claude/claude_compact_statusline.py`.

Claude's native auto-compaction stays on; `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not set, since a lower fixed threshold isn't quota-aware and could rewrite a still-warm prefix early. No automatic external `/compact` for either agent: a visible recommendation beats injecting commands into an interactive session without a supported quota-aware trigger.

### Idle compaction

`llm/idle_compact.py` cuts the cost of returning to a large Claude session after its prompt cache expired. On a subscription the cache lives 1 hour; the next call rewrites the whole context at 2× input price. Across nine measured sessions these rebuilds were 27% of Claude cost (largest: 6 days, median context 415K, 20 idle rebuilds of ~360K). RTK, Serena and Headroom shrink tool output and can't touch this; Claude's auto-compaction starts only near 1M tokens.

Fix: write a checkpoint while the cache is warm; on return, optionally continue from it in a fresh chat. Estimated idle-resume share: 27% → ~7% when the fresh chat is chosen.

Both clients checkpoint any session with positive input usage, including a 65K session; the quota safeguard keeps its 120K floor. Idle compaction handles ordinary idle gaps; the quota warning handles the pause forced by an exhausted quota, when the checkpoint turn itself can't run. In Codex the quota warning stays silent on a prompt after a 30-minute gap, where the idle guard handles the resume.

#### One idle period (Codex)

The `Stop` hook runs `arm --client codex` in the background (`async: true`, `timeout: 11000`). After 27 minutes without new activity, it saves a local checkpoint with the original request, latest reply and request, a redacted transcript with turn pointers, and the repository digest. A new turn or newer arm token cancels the worker. Timing is 90% of the [documented default minimum cache lifetime](https://developers.openai.com/api/docs/guides/prompt-caching#cache-lifetime) of 30 minutes for GPT-5.6 and later, measured from the last token-usage event. The hook has no per-session expiry signal; cache entries may survive longer. Earlier models and other providers may have different retention policies.

After a 30-minute gap, the prompt guard offers the checkpoint once. Run `$pitstop` in that thread (the guard blocks it and hands its checkpoint off) and then `/clear` (the `SessionStart` `clear` hook loads it), or `$pitstop` in a fresh thread, then paste the prompt, or resend the prompt to keep the full session. If no valid checkpoint exists, it suggests `/compact` without blocking. The installer adds `llm/codex/pitstop/SKILL.md` to `~/.agents/skills/pitstop/`, shared by personal and work Codex profiles. Later accepted prompts invalidate the checkpoint.

[Codex background hooks](https://developers.openai.com/codex/hooks#how-background-hooks-run) cannot wake an idle session and are cancelled when the session ends. Codex therefore saves transcript excerpts locally rather than asking the model to write a summary; it makes no extra model request and does not run `/compact` automatically.

#### One idle period (Claude)

1. **Reply arrives.** The `Stop` hook starts `arm` in the background (`asyncRewake: true`, `timeout: 4000`). It sleeps until 54 min after the last call (0.9 of cache lifetime, the native compactor's fraction); a new message or newer arm token cancels it.
2. **At 54 min** `arm` exits 2, waking the session with a checkpoint request plus a script-built digest. The model writes the checkpoint without tools; the turn reads from cache and renews it for an hour, keeping the full session cheap until ~1h54m after last activity.
3. **Next `Stop`** stores the reply's text blocks (never thinking) as the checkpoint, plus a cleaned transcript.
4. **Return after expiry.** The `UserPromptSubmit` guard blocks the first prompt once, shows rebuild size and checkpoint time, and repeats the prompt. The user either runs `/pitstop` in that session (the guard blocks it and hands that session's checkpoint off) and then `/clear` (the `SessionStart` `clear` hook loads it into the fresh session within 10 minutes, so the old session ID keeps its checkpoint), runs `/pitstop` in a new chat, or resends to keep the full session.
5. **`/pitstop`** (`llm/claude/pitstop.md`, installed to each profile's `commands/`) runs `idle_compact.py resume`: the newest checkpoint for the current project whose chat had no prompt since, in fixed section order, then the digest, repo drift since the checkpoint (HEAD moves, uncommitted files), and a resume protocol: state goal and first next step, ask to confirm, treat Decisions and Dead ends as settled, fetch missing detail with `turn` or `search`, never read `transcript.md` whole. `/clear` without a preceding `/pitstop` keeps stock behavior.

#### Checkpoint content

The script extracts what can be listed exactly; the model writes only what needs judgment. The digest lands at the end of context, giving the model a whole-session index right before it writes.

| Part | By | Holds |
|---|---|---|
| Goal, Done, Decisions, Dead ends, Current state, Constraints, Next steps | Model | Goal in the user's words; decisions with reason and rejected alternative; abandoned approaches; a first next step concrete enough to start |
| Pointers | Model | Turn numbers with detail too long to carry (traces, pasted specs) |
| Digest | Script | Non-routine requests with turn numbers, edited files with counts, repo branch/HEAD/uncommitted/commits, last error, open todos; capped ~3K tokens |

Test for every item: would a fresh session act wrongly or waste time without it? Keep exact names of files, functions, commands, errors; drop routine operations, tool output, reasoning. A later checkpoint in the same session updates the earlier one (kept as `checkpoint-<n>.md`). Length 300–1,200 words.

#### Storage and lookup

```text
~/.local/state/idle-compact/        mode 0700
  sessions/<id>.{arm,fired,stored,guard}       one writer each; 7 days
  checkpoints/<project>/<date>-<id>/            one folder per session; 30 days
    checkpoint.md    metadata header + model sections
    digest.json      script-extracted facts
    transcript.md    one `## T<n> · kind · time` heading per turn; tool output
                     cut to 2K chars, thinking dropped, secrets redacted
```

Plain files, one folder per session: no shared writer, no locks, atomic rename on every write. `idle_compact.py search "<words>"` (`--all`, `--session`, `--since <days>`) ranks checkpoints and transcript turns by matched words, returning ≤ 5 snippets; `idle_compact.py turn <session> T<n>` returns one turn with its neighbors' headings. Both cap output at 2,000 chars. SQLite, a local search engine, Postgres and vector stores were rejected: data never crosses chats and output is capped anyway.

#### Rejected alternatives

| Option | Why not |
|---|---|
| Native idle compactor (`tengu_sunny_locket`) | Server flag only; `arm` steps aside when its mode is `compact` |
| Keep-warm pings | Context never shrinks; each hour away still costs ~0.1× context |
| Inject `/compact` into the open session | No interface in the VS Code extension |
| Headless `claude -p --resume <id> /compact` | The open panel keeps appending its in-memory history |
| Compact inside Headroom | The model would see a summary the client never shows |

#### Settings and safety

- `IDLE_COMPACT=off` disables the hooks. `IDLE_COMPACT_TEST_SECONDS` replaces either client's idle wait, for live tests only.
- Any parse failure exits 0; a killed sleeper changes nothing since state is written only at fire time.
- Common secrets (API keys, bearer tokens, private keys, password assignments) are redacted before writing.
- The old session stays resumable, so a checkpoint that misses a detail loses nothing.

#### Open questions

- Does Codex show a non-blocking `systemMessage` from `UserPromptSubmit`?
- What do Claude Code's `precomputeCompactionEnabled` and `awaySummaryEnabled` do? They may cover part of this natively.
- What does the checkpoint turn cost at `xhigh` effort?
- Do Codex hooks expose cache TTL or expiry metadata for policies other than the GPT-5.6+ default?
- Does the new chat follow the resume protocol's confirm step?
- Does Headroom keep the cache warm across 10–60 min gaps? On 0.39.1 the checkpoint turn read 25K and rewrote 480K; re-measure on 0.40.0 (#3934).

### Token-profiler

`token-profiler codex | codex-work | claude | claude-work`. Model-call windows split after gaps > 30 min and report: context size on the first resumed call; first-call fresh input and its share of the window's fresh input; later-call fresh total and average; cold-start, idle-resume and post-compaction attribution where the transcript shows enough. Claude records add exact cache-read and cache-creation counts. Reads local session files only; no model/API requests.

## 8. How the tools reinforce each other

Prevent waste as early as possible — earlier cuts remove downstream work entirely:

Ponytail (unneeded implementation) → Serena (unneeded repo reads) → Context7 (stale/guessed API knowledge) → RTK (shell-output volume) → Headroom (compress what remains).

**Example — "Deleted users still appear in /users."** Without the stack: broad grep, whole-file reads, patch only the named route, noisy full test run, large logs/diffs over several turns. With it:

1. **Ponytail**: find the root cause, fix it once in the shared path.
2. **Serena**: find the endpoint, shared service/repository symbol, and all callers.
3. **Context7**, only if the fix depends on third-party behavior.
4. Read only required bodies and docs; make the smallest root-cause diff.
5. **RTK** compacts test/git output; **Headroom** compresses the rest for the next call.
6. **Ponytail review** checks the diff for accidental abstractions or files.

## 9. Configuration ownership

Each piece has exactly one owner:

| Piece | Owner | Mechanism |
|---|---|---|
| Serena, Context7 MCP | `llm/ai-install.sh` `configure_agent_mcps` | Removed and re-added at user scope in all four profiles on every run |
| Headroom routing + service | `headroom install apply` + `agent_config.py headroom-work` | Config entries pointing at the shared proxy (§7) |
| Agent policies | `llm/ai-install.sh` `install_global_agents` | `codex/__AGENTS.md` → both Codex homes; `claude/__AGENTS.md` → both Claude homes; RTK imports added by `configure_rtk` |
| Spec Kit CLI | `llm/ai-install.sh` `install_ai_tools`, `install_global_agents` | `uv tool install --upgrade specify-cli`; project initialization stays explicit through `/speckit-init` (Claude) or `$speckit-init` (Codex) |
| Superpowers | `llm/ai-install.sh` `install_superpowers` | Reuses an enabled curated/upstream plugin; otherwise installs the upstream plugin in both Codex homes and `superpowers@claude-plugins-official` in both Claude homes |

`headroom wrap` is not used: it would register its own Serena code-memory MCP (unless `--code-memory none`) and rewrite Codex's `config.toml`. If a profile still shows a `headroom` MCP server (`headroom mcp serve`) from an earlier `wrap`, remove it with `claude mcp remove --scope user headroom`.

Two Serena servers on one project mean duplicate tools, duplicate indexing/LSP processes, more memory, confused activation/state, and uncertain tool choice.

## 10. Hook coexistence

All three can use Codex lifecycle hooks with distinct jobs: RTK → `PreToolUse` Bash rewriting; Serena → activation/reminders/cleanup; Ponytail → session activation, mode tracking, subagent rules. RTK 0.49.0 `init --codex` manages instructions; this repo separately merges the RTK adapter into user-level `hooks.json`; Serena documents user-level hooks in `~/.codex/hooks.json`; Ponytail's plugin carries its own. Merge entries, never replace a hook file blindly, and confirm in Codex's hook view that all are active. Shell commands bypass hook trust; other launchers still require review.

## 11. `AGENTS.md`

Describe behavior, not install manuals: prefer Serena for semantic exploration; Context7 conditionally for third-party APIs; let RTK's hook handle supported commands; apply Ponytail's minimum-correct discipline; treat Headroom as transparent and never rely on compression for correctness; minimize context upstream instead of producing noise "because it will be compressed". `llm/codex/__AGENTS.md` and `llm/claude/__AGENTS.md` stay short because every always-on line costs context. If an installer adds a managed RTK block, preserve or reconcile it rather than deleting it.

Both agent templates include structured delivery routing. Spec Kit owns feature scope and progress; Superpowers supplies implementation disciplines within the existing Ponytail and retrieval rules. Resolve conflicts in this order: explicit user requirements, applicable agent policy, project constitution, active specification, plan, tasks, then Superpowers defaults.

## 12. Task workflow

1. Understand the request.
2. Activate/check Serena when semantic code work is needed; locate symbols and references.
3. Query Context7 narrowly if third-party behavior matters.
4. Apply Ponytail's ladder; edit the fewest files.
5. Run the narrowest useful validation (RTK compacts output).
6. Inspect the final diff; `@ponytail-review` for non-trivial changes when available.
7. Headroom optimizes transport automatically — never an excuse for broad reads or huge commands.

### Structured feature delivery in Codex and Claude

`llm/ai-install.sh` installs `specify-cli` and Superpowers without initializing the current repository. Superpowers uses the upstream `obra/superpowers` Codex marketplace, whose current name is `superpowers-dev`. An already enabled `superpowers@openai-curated` or `superpowers@superpowers-dev` is reused, avoiding a second installation. The curated marketplace could not be registered in the work profile on this host, so the upstream plugin path was verified in both profiles. Claude installs `superpowers@claude-plugins-official` from the official marketplace and reuses an enabled `superpowers@superpowers-dev`. Do not also expose a manual Superpowers skill symlink.

Spec Kit is project-local: its skills call scripts under each project's `.specify/`, so it cannot run globally. The global `/speckit-init` command (`llm/claude/speckit-init.md`) and `$speckit-init` skill (`llm/codex/speckit-init/SKILL.md`) initialize the current project on request, refusing a dirty tree. The manual equivalent for an existing project, after committing or stashing its current work:

```bash
specify init --here --force --integration codex --integration-options="--skills"
specify integration install claude
rtk git status --short
rtk git diff --stat
rtk git diff -- .specify .agents .claude
```

`specify integration install claude` also adds Claude to a project already initialized for Codex without overwriting the constitution; `specify integration status` lists both. Codex skills live under the project's `.agents/skills/` and Claude skills under `.claude/skills/`; `.specify/` holds shared project tooling and `specs/<feature>/` holds persistent feature artifacts. Create the project constitution once with `$speckit-constitution` (`/speckit-constitution` in Claude), then use this bounded feature workflow (Claude uses the same names with `/`):

```text
$speckit-specify
$speckit-clarify
$speckit-plan
$speckit-tasks
$speckit-analyze
$speckit-implement
$speckit-converge
```

Clarify only when ambiguity matters; analyze meaningful features before implementation. During implementation, load applicable Superpowers TDD, systematic debugging, and verification skills. Keep `@ponytail-review` before commits changing more than about 30 lines of code. Update the active spec, plan, or tasks when implementation changes them; do not create a parallel Superpowers design, plan, or task ledger. Without Spec Kit, the normal workflow applies; Superpowers brainstorming, writing-plans, worktrees, and subagent orchestration run only on request and produce a short inline outline rather than a document.

Keep the optional Spec Kit Git extension, Superpowers worktree/subagent orchestration, and bridge extensions out of the initial setup. Existing idle checkpoints and pitstop supply session context; the active Spec Kit artifacts remain the feature ledger. The `code` shell function selects the personal Codex home; other IDE launchers need their profile checked separately.

Validated on October 12, 2026: Spec Kit 1.1.3 generated all ten Codex skills, including converge, in a temporary project; Superpowers 7.0.0 was installed and enabled in both Codex profiles; all 63 unit tests passed; `bash llm/smoke-test.sh --strict` reported 71 passes with no warnings or failures. The smoke test checks CLI startup, plugin enablement, and installed policy consistency. Fresh VS Code skill discovery and model-driven workflow behavior remain unverified: restart Codex and explicitly request `systematic-debugging` in each host/profile you use.

Validated on October 13, 2026: Spec Kit 1.1.3 added all ten Claude skills to a Codex-initialized project with `specify integration install claude`, preserving the constitution; Superpowers 6.4.1 was installed and enabled in both Claude profiles, and a second installer run reused it; `bash llm/smoke-test.sh --strict` reported 75 passes with no warnings or failures. Restart Claude Code to load the plugin.

See [the integration specification](../codex-superpowers-speckit-integration.md) for routing and rollout details, [Superpowers upstream](https://github.com/obra/superpowers), and [Spec Kit](https://github.com/github/spec-kit).

## 13. When to bypass a layer

| Situation | Action |
|---|---|
| Serena can't handle a file/language | Built-in filesystem/search tools, narrowly |
| Dependency docs unnecessary/stable | Skip Context7 |
| Context7 lacks the library/version | Authoritative upstream docs, or inspect the installed package narrowly |
| Exact raw output required | `RTK_DISABLED=1 <command>` |
| Compression may have hidden a detail | Headroom retrieval if available, or a narrow raw rerun |
| User explicitly requests an abstraction/dependency/design | Ponytail follows the requirement |
| Security, trust-boundary validation, accessibility, data-loss protection | Never simplified away |
| Tool unavailable/broken | Continue with built-ins; correctness never depends on the stack |

## 14. Expected impact

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
| Runtime overhead | Very low | Index/LSP | Retrieval/network | Very low | Proxy/compression |
| Main failure mode | Underbuilding | LSP/tool mismatch | Unnecessary/stale retrieval | Hidden raw detail | Over-compression / proxy debugging |

Not additive: if RTK reduces a 10,000-line test log to a failure summary, Headroom has little left to compress.

## 15. What to measure

Per task: model input/output tokens; Headroom savings/ratio; raw vs RTK shell bytes; full-file reads; Serena symbolic retrievals; Context7 lookups and whether they changed decisions; diff LOC; files changed; dependencies added; latency; test pass/fail; reruns caused by missing context.

Same-thread quota-reset experiment, one row per pause: context just before and after `/compact`; pause duration; first resumed call's total, cached and fresh input; fresh input across the first ten resumed calls; Headroom savings; provider-cache warmth. Compare against a similar uncompacted cycle; don't sum Headroom, RTK or cache percentages (scopes overlap).

The metric that matters is **correct work per token and per unit time**, not maximum compression.
