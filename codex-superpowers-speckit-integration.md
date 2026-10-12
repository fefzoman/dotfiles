# Incorporating Superpowers and GitHub Spec Kit into Codex

**Target environment:** personal/work Codex CLI profiles and Codex in VS Code, within the shared Codex/Claude toolchain maintained by `llm/`.

**Existing foundation:** profile policies, Ponytail, Serena/Context7, RTK hooks, Headroom config routing, context warnings, idle checkpoints, and the local `token-profiler`.

**Goal:** add structured feature delivery and stronger implementation discipline without creating duplicate plans, bloating context, or weakening the existing global policy.

---

## 1. Recommended architecture

### Existing `llm/` foundation

`llm/ai-install.sh` owns AI tool installation and profile configuration. Executing it installs tools; sourcing it loads shell functions and aliases. `llm/agent_config.py` merges profile configuration and hooks. The proposed Superpowers/Spec Kit adoption below is not implemented by this installer.

| Layer | Repository source / behavior |
|---|---|
| Codex policy source | `llm/codex/__AGENTS.md` |
| Claude policy source | `llm/claude/__AGENTS.md` |
| Personal/work Codex profiles | `~/.codex`, `~/.codex-work`; `codex-work` selects the latter through `CODEX_HOME` |
| Personal/work Claude profiles | `~/.claude`, `~/.claude-work`; `claude-work` selects the latter through `CLAUDE_CONFIG_DIR` |
| Shell / VS Code launch | `llm/ai-install.sh`; the `code` function selects personal Codex and clears `CLAUDE_CONFIG_DIR` |
| Engineering policy | Ponytail plugin installed separately in all four profiles |
| Repository / external retrieval | One configured Serena server and Context7 per profile; `llm/context7_version_guard.py` checks pinned versions |
| Shell output | RTK; `llm/codex/codex_rtk_hook.py` adapts its rewrite contract for Codex |
| Transport | Shared persistent Headroom proxy, reached through each profile's configuration |
| Context safeguards | `llm/codex/codex_compact_warning.py`, `llm/claude/claude_compact_statusline.py`, and shared `llm/idle_compact.py` |
| Checkpoint resume | Codex skill `llm/codex/pitstop/SKILL.md`; Claude command `llm/claude/pitstop.md` |
| Measurement / installation checks | `llm/token-profiler/`, `llm/smoke-test.sh` |

**Policy installation:** `install_global_agents` in `llm/ai-install.sh` installs each agent-specific policy source above into its personal and work profiles. Policy checks in `llm/smoke-test.sh` compare installed policies against the corresponding source and validate each profile's RTK import.

The policy installation targets remain `AGENTS.md` in both Codex homes and `CLAUDE.md` in both Claude homes. Repository `__AGENTS.md` files are source templates, not automatically discovered project instructions.

### Proposed delivery layer

Use the two systems for different responsibilities:

```text
                    Active profile AGENTS.md
            minimal change / retrieval / shell / validation
                                │
                                ▼
                     GitHub Spec Kit
              persistent feature source of truth
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
               spec.md       plan.md       tasks.md
                  │             │             │
                  └─────────────┴──────┬──────┘
                                      ▼
                              implementation
                                      │
                                      ▼
                              Superpowers
                      implementation-time disciplines
                   TDD / debugging / verification / review
                                      │
                                      ▼
                              tests + final diff
                                      │
                                      ▼
                           speckit converge
```

### Responsibility split

| Concern | Owner | Rule |
|---|---|---|
| Global coding behavior | Active profile `AGENTS.md` + Ponytail | Keep minimal-change, retrieval, RTK/Headroom, Git, and finish rules |
| Requirements / intended behavior | Spec Kit | `spec.md` is the feature contract |
| Technical design | Spec Kit | `plan.md` is the implementation design |
| Work breakdown / progress | Spec Kit | `tasks.md` is the task ledger |
| Clarification / artifact consistency | Spec Kit | Use clarify / analyze / converge |
| TDD | Superpowers | Apply during implementation when tests are appropriate |
| Root-cause debugging | Superpowers | Use `systematic-debugging` rather than ad-hoc guessing |
| Verification before completion | Superpowers | Use `verification-before-completion` |
| Code-review discipline | Ponytail; optional Superpowers review | Keep `ponytail-review` before commits changing more than about 30 lines of code |
| Session continuity | Existing idle checkpoint / pitstop tooling | Resume the active Spec Kit artifacts; checkpoints do not become another task ledger |
| Extra plan generation | **Neither** | Never maintain a second parallel plan for the same feature |

The central rule is:

> **Spec Kit owns feature state; Superpowers improves how implementation work is performed.**

Do not run two independent specification/planning pipelines for the same feature.

---

## 2. Why this division is preferable

Spec Kit is designed around persistent Markdown artifacts:

```text
Specify → Plan → Tasks → Implement → Converge
```

For Codex, the current Spec Kit integration is skills-based and installs project-local skills under:

```text
.agents/skills/
```

Codex invokes them with forms such as:

```text
$speckit-specify
$speckit-plan
$speckit-tasks
$speckit-implement
$speckit-converge
```

Superpowers also provides planning and design skills, including `brainstorming` and `writing-plans`, but using those in parallel with Spec Kit would create two competing artifact sets.

For a Spec Kit-managed feature, avoid this:

```text
Superpowers brainstorming
        ↓
Superpowers design
        ↓
Spec Kit spec
        ↓
Spec Kit plan
        ↓
Superpowers writing-plans
        ↓
Spec Kit tasks
```

Prefer:

```text
Spec Kit specify
        ↓
Spec Kit clarify
        ↓
Spec Kit plan
        ↓
Spec Kit tasks/analyze
        ↓
Spec Kit implement
        │
        ├── Superpowers TDD
        ├── Superpowers systematic debugging
        ├── Superpowers verification
        └── Superpowers review
        ↓
Spec Kit converge
```

This reduces duplicated reasoning and makes one repository-visible artifact chain authoritative.

---

## 3. Installation

The commands below are adoption steps, not existing `llm/ai-install.sh` behavior. Keep reusable agent setup under `llm/`; keep Spec Kit initialization and feature artifacts in the target project. Resolve the policy migration prerequisite in §1 before running the installer. Once resolved, its installation check is `bash ./llm/smoke-test.sh`; this checks the existing stack, not Superpowers/Spec Kit discovery or runtime hook trust.

### 3.1 Superpowers

#### Preferred supported Codex path

Current Superpowers documentation exposes Superpowers through the Codex plugin marketplace for Codex surfaces that support it.

In Codex CLI:

```text
/plugins
```

Search for:

```text
superpowers
```

and install the plugin. Repeat in both `codex` and `codex-work` sessions: plugin installation/configuration is profile-specific, just as `install_ponytail` installs separately into both Codex homes. Do not also expose the same skills through the manual path below.

#### Manual/native-skill path

The upstream Codex guide also documents native skill discovery:

```bash
git clone https://github.com/obra/superpowers.git ~/.codex/superpowers

mkdir -p ~/.agents/skills

ln -s ~/.codex/superpowers/skills \
  ~/.agents/skills/superpowers
```

Restart Codex after installing.

Verify the filesystem side:

```bash
rtk ls -la ~/.agents/skills/superpowers
rtk ls ~/.codex/superpowers/skills
```

`~/.agents/skills` is a shared user skill location, also used by the existing Codex `pitstop` installation. The checkout under `~/.codex/superpowers` is the symlink target, not a second plugin installation. Check discovery in both profiles.

#### VS Code Codex note

The Superpowers upstream installation documentation explicitly describes Codex CLI/App paths. For a VS Code Codex workflow, verify skill discovery in a **fresh IDE Codex session** instead of assuming that a CLI/plugin installation is automatically visible in every host.

A useful behavioral verification is to explicitly request one known skill, for example:

```text
Use the Superpowers systematic-debugging skill for this bug.
```

The installed `code` shell function launches VS Code with `CODEX_HOME=~/.codex` and no `CLAUDE_CONFIG_DIR`; it does not select the work profile. Launchers outside that function need their profile checked separately. Headroom routing lives in profile configuration, so IDE sessions do not need `headroom wrap`.

If Codex cannot discover it, fix discovery before adding any policy that assumes Superpowers is present.

#### Do not copy Superpowers into `AGENTS.md`

Do **not** paste full Superpowers skills into the global `AGENTS.md`.

Codex skills are intended to be discovered by name/description and loaded when relevant. Keeping the full workflows out of the always-present global instruction file prevents unnecessary baseline context growth.

### 3.2 GitHub Spec Kit

Install `specify-cli`:

```bash
uv tool install specify-cli
```

Verify:

```bash
specify version
```

For an **existing repository**, first commit or stash current work so the initialization diff is reviewable.

Then, from the repository root:

```bash
specify init --here --force --integration codex
```

The current Codex integration is skills-based and installs Spec Kit skills in:

```text
.agents/skills/
```

Review the initialization diff before continuing:

```bash
rtk git status
rtk git diff --stat
rtk git diff -- .specify .agents
```

These commands work with the manual RTK fallback. Automatic rewriting requires a trusted, verified hook in the current host/session; `rtk init --codex` and the smoke test do not establish that trust.

#### Do not enable optional Git behavior initially

Spec Kit's Git extension is optional:

```bash
specify extension add git
```

Do **not** add it during the first adoption phase unless you specifically want Spec Kit to own feature branch/worktree behavior.

You already have Git/release conventions. Adding Spec Kit Git management and Superpowers worktree behavior at the same time creates unnecessary overlap.

---

## 4. Minimal global `AGENTS.md` integration

Do not replace the existing global policy.

Add the Codex routing section to `llm/codex/__AGENTS.md`, preferably between **Retrieval** and **Shell output**, and install it into both `~/.codex/AGENTS.md` and `~/.codex-work/AGENTS.md`. Editing only an installed copy is not durable: the installer replaces policy text from its repository source. Preserve each profile's RTK reference.

Keep Claude policy in `llm/claude/__AGENTS.md` with the same structured delivery routing. Verify command and skill availability in each agent's host before using them.

### Recommended block

```md
## Structured delivery (Spec Kit + Superpowers)

- For a feature managed by Spec Kit, its active specification, plan, and tasks are the persistent source of truth for scope and implementation state.
- Do not create a parallel Superpowers design or implementation plan for the same Spec Kit feature. Skip equivalent `brainstorming` / `writing-plans` stages unless explicitly requested or no Spec Kit artifacts exist.
- During implementation, use applicable Superpowers disciplines within the existing Ponytail, retrieval, validation, and review rules; do not duplicate Spec Kit artifacts or start another Serena server.
- If implementation discoveries change requirements, design, or remaining work, reconcile the relevant Spec Kit artifact instead of creating a second planning document.
- Load only the active feature artifacts and the skills needed for the current step; do not read the whole specs tree or skill library.
- Small, local changes do not require the Spec Kit lifecycle unless explicitly requested or the repository requires it.
```

This block is intentionally short. The detailed workflow belongs in this document and in the tools' own skills, not in global always-loaded context.

---

## 5. Policy hierarchy

Use this semantic authority when the tools disagree:

```text
Explicit user requirement
        ↓
Applicable AGENTS.md policy
        ↓
Project constitution
        ↓
Active Spec Kit specification
        ↓
Spec Kit plan
        ↓
Spec Kit tasks
        ↓
Superpowers workflow defaults
```

Codex discovers global instructions from the active `CODEX_HOME` (default `~/.codex`), then project instructions from repository root toward the current working directory. `AGENTS.override.md` takes precedence at each level, and more local instructions can override broader ones. The work profile therefore has its own global policy. Review the active profile and repository-local policy when behavior is surprising.

A Superpowers skill should improve execution discipline, not silently rewrite product requirements or invalidate a Spec Kit decision.

---

## 6. Project adoption workflow

For an existing repository:

### Step 1 — Initialize Spec Kit

```bash
specify init --here --force --integration codex
```

Review exactly what was added.

### Step 2 — Create the project constitution once

In Codex:

```text
$speckit-constitution
```

The constitution should capture **project-level truths**, not repeat every global rule.

Good examples:

- public API compatibility requirements
- migration/rollback requirements
- repository-specific test expectations
- security boundaries
- architecture boundaries that must be preserved

Avoid copying the whole global `AGENTS.md` into the constitution.

### Step 3 — Create a bounded feature spec

```text
$speckit-specify <feature outcome and constraints>
```

For existing systems, specify the intended change rather than trying to retroactively specify the whole repository.

### Step 4 — Clarify important ambiguity

For production-impacting or ambiguous work:

```text
$speckit-clarify
```

Skip it for straightforward work where the specification is already precise.

### Step 5 — Produce the technical plan

```text
$speckit-plan
```

Review it against:

- current architecture
- existing dependencies
- Ponytail / "build less"
- current callers and compatibility boundaries
- Serena-derived repository facts
- Context7 only where external/version-sensitive behavior needs confirmation

Do **not** additionally invoke Superpowers `writing-plans` for the same feature.

### Step 6 — Produce tasks

```text
$speckit-tasks
```

For non-trivial features, run:

```text
$speckit-analyze
```

before implementation to catch cross-artifact inconsistencies.

### Step 7 — Implement

```text
$speckit-implement
```

During actual implementation, Superpowers becomes useful.

Use the relevant implementation discipline rather than the Superpowers end-to-end planning pipeline:

```text
new behavior
    → test-driven-development

unexpected failure / unclear cause
    → systematic-debugging

before claiming complete
    → verification-before-completion

meaningful diff
    → requesting-code-review / review discipline
```

Your existing global retrieval rules remain active:

```text
repository code     → Serena
external API/lib    → Context7
known stable fact   → neither
```

Keep the existing RTK hooks and manual fallback. The shell `codex` function bypasses hook trust for personal/work CLI sessions; sessions launched elsewhere still require hook review and runtime verification. Headroom is transport configured in each profile, not a shell wrapper or another planning/retrieval owner. Do not add a second Serena instance, and retrieve any detail hidden by compression before relying on it.

### Step 8 — Converge

After implementation and validation:

```text
$speckit-converge
```

If convergence adds legitimate remaining work, update/execute those tasks and converge again.

The desired terminal state is:

```text
spec
  = implemented behavior
plan
  = actual architecture
tasks
  = completed work
tests
  = evidence
diff
  = scoped
```

---

## 7. Which Superpowers skills to use

### Use routinely

#### `test-driven-development`

Use for behavior changes and bug fixes where a useful automated test can demonstrate the behavior.

It complements the existing "smallest correct change" policy:

```text
failing evidence
    ↓
minimal implementation
    ↓
passing evidence
    ↓
refactor only when justified
```

Do not manufacture low-value tests solely to satisfy process.

#### `systematic-debugging`

Use when the cause is not already established.

This aligns with the existing global rule to fix the shared root cause instead of patching a symptom.

#### `verification-before-completion`

Use before Codex claims a task or feature is complete.

This complements the existing requirement to validate using the narrowest useful check.

#### Review skills

Use when the diff is non-trivial or risk-bearing.

Run the existing `ponytail-review` before committing a diff that adds or changes more than about 30 lines of code (excluding config and generated files). Use the invocation exposed by the current host, such as `@ponytail-review` or `$ponytail-review`. Superpowers review does not replace this rule; avoid a second review unless it answers a concrete remaining concern.

### Use selectively

#### `brainstorming`

Useful for early exploration when there is **no active Spec Kit feature** yet.

If the output becomes real project work, transfer the approved decisions into the Spec Kit specification and treat Spec Kit as the durable source.

Do not preserve two authoritative design documents.

#### `using-git-worktrees`

Use only if you intentionally want Superpowers to own workspace isolation.

Do not combine it casually with a Spec Kit Git extension or an existing repository automation that already controls feature branches/worktrees.

#### `subagent-driven-development` / `executing-plans`

These Superpowers workflows are designed around Superpowers plans. Follow the active session's delegation rules; installing a skill does not itself authorize subagent work.

Do not make them the default executor for a Spec Kit `tasks.md` unless you have deliberately introduced an integration layer that translates/coordinates the two systems.

For initial adoption, prefer:

```text
Spec Kit orchestration
+
individual Superpowers engineering disciplines
```

rather than:

```text
Spec Kit orchestration
+
Superpowers orchestration
```

---

## 8. What not to combine

Avoid these combinations by default.

### Duplicate planning

```text
$speckit-plan
+
Superpowers writing-plans
```

Choose Spec Kit.

### Duplicate specification/design

```text
$speckit-specify
+
Superpowers brainstorming saved as another binding design
```

Explore with one, but keep one durable source of truth.

### Duplicate task ledgers

```text
tasks.md
+
another Superpowers checklist tracking the same implementation
```

Keep `tasks.md` authoritative.

### Duplicate branch/worktree managers

```text
Spec Kit Git extension
+
Superpowers using-git-worktrees
+
custom repository branch automation
```

Choose one owner.

### Always-on skill text in `AGENTS.md`

Do not copy full skill instructions into global policy.

That turns conditional context into permanent context on every Codex call.

---

## 9. Task-size routing

Use the following routing rather than forcing Spec Kit onto every change.

| Work type | Spec Kit | Superpowers |
|---|---:|---|
| Typo / tiny config change | No | Usually no |
| Small obvious refactor | No | Verification; TDD only if behavior changes |
| Local bug with established cause | Usually no | TDD + verification |
| Bug with unclear cause | Usually no | Systematic debugging + TDD + verification |
| Cross-module bug with behavior ambiguity | Maybe | Debugging + TDD + verification |
| Normal feature | Yes | TDD + verification + review |
| Large feature / architecture change | Yes, full workflow | TDD + debugging + verification + review |
| Early idea exploration | Optional | Brainstorming can be useful |
| Long multi-phase feature | Yes; split scope before context becomes huge | Use execution skills selectively |

This preserves Ponytail: process is also something to keep minimal.

---

## 10. Context and token discipline

This integration should **reduce re-discovery**, not create permanent framework overhead.

### Keep global instructions small

`AGENTS.md` is injected into Codex context automatically. Do not turn it into a manual for either framework.

Keep only routing and precedence rules there.

### Use skills conditionally

Skills are valuable because Codex can discover their metadata and load the detailed instructions when the workflow applies.

Do not eagerly read every Superpowers or Spec Kit skill at session start.

### Load only the active feature

Prefer:

```text
active spec.md
active plan.md
relevant task section
relevant code symbols
one applicable skill
```

over:

```text
all specs
all plans
all tasks
all skills
whole repository files
```

### Bound implementation batches

If a feature is large, do not keep one huge implementation context alive merely because `tasks.md` is long.

Prefer bounded task groups or sub-features. Spec Kit explicitly recommends limiting work scope before resorting to heavier decomposition.

### Reuse context safeguards and checkpoints

The existing Codex hook and Claude status line warn when context reaches 120,000 input tokens and an active quota window reaches 85% usage. They recommend `/compact`; they do not execute it automatically.

Separately, `llm/idle_compact.py` uses Stop and UserPromptSubmit hooks to prepare idle checkpoints and guard large cold resumes. Codex creates local transcript excerpts; Claude can request a summary through its supported idle hook. Resume from the project directory with `$pitstop` in Codex or `/pitstop` in Claude. Reload the active feature's spec, plan, and task section, and reconcile actual progress there. A checkpoint supplies session context, not a parallel feature plan. Retrieve missing details with the checkpoint's `turn` and `search` commands instead of reading the whole transcript.

### Measure instead of guessing

Use the installed `token-profiler` with an explicit profile selector:

```bash
token-profiler codex-work current
token-profiler codex-work sessions
token-profiler codex-work top --by session
token-profiler codex-work top --by file
token-profiler codex-work top --by command
```

Use `codex`, `claude`, or `claude-work` for the other profiles. The installer removes the obsolete `codex-usage` command. The profiler reads local sessions without model/API requests; exact token totals, estimated RTK savings, Headroom's global ledger, and observed tool activity have different scopes and must not be added. Ponytail savings are not inferred from avoided work. JSON reports can contain local paths and prompt/command text.

Compare equivalent work before and after adoption.

Track at least:

```text
input tokens
fresh input
cached input
output
model calls
compactions
rework/corrections
human interventions
test failures caused by wrong implementation
```

A framework is beneficial when the extra process context is paid back through less re-reading, fewer wrong turns, and more reliable implementation.

---

## 11. Suggested experiment

Do not roll both tools into every project immediately.

Use one medium-size feature and compare it with a recent similar feature.

### Baseline

```text
global AGENTS.md
+
normal Codex workflow
```

### Trial

```text
global AGENTS.md
+
Spec Kit artifacts
+
selected Superpowers implementation skills
```

Compare:

| Metric | Baseline | Trial |
|---|---:|---:|
| Total input | | |
| Fresh input | | |
| Cached input | | |
| Output | | |
| Model calls | | |
| Compactions | | |
| Repeated file reads | | |
| Corrections / rework | | |
| Human interventions | | |
| Final validation failures | | |

Do not optimize for token count alone. A modest token increase can be worthwhile if rework and incorrect implementations fall materially.

---

## 12. Optional integration bridges

Spec Kit's current community extension catalog contains projects intended to bridge Spec Kit and Superpowers, including a **Superpowers Bridge**, a **Superpowers Implementation Bridge**, and **Superspec**.

Do **not** start there.

First establish the simple boundary:

```text
Spec Kit = artifacts/orchestration
Superpowers = implementation discipline
```

Only add a bridge if you later have a concrete requirement such as:

- execute Spec Kit tasks through Superpowers subagents
- carry one shared progress ledger between both systems
- translate Spec Kit planning artifacts into a Superpowers execution workflow

A bridge adds another process layer and should solve an observed problem, not be installed speculatively.

---

## 13. Recommended repository structure

A repository after adoption should look conceptually like:

```text
repo/
├── AGENTS.md                  # only repo-specific overrides, if needed
├── .agents/
│   └── skills/
│       ├── speckit-...
│       └── ...
├── .specify/
│   ├── ...
│   └── ...
├── specs/
│   └── <active-feature>/
│       ├── spec.md
│       ├── plan.md
│       ├── tasks.md
│       └── ...
└── src/
```

Superpowers can remain global rather than being copied into every repository:

```text
~/.agents/skills/superpowers/
```

This keeps:

```text
global reusable engineering skills
            separate from
project-local product/design state
```

---

## 14. Day-to-day workflow examples

### New feature

```text
1. $speckit-specify
2. $speckit-clarify        # when needed
3. $speckit-plan
4. review plan
5. $speckit-tasks
6. $speckit-analyze       # meaningful feature
7. $speckit-implement
   - use Superpowers TDD while changing behavior
   - use systematic-debugging only if failures require diagnosis
   - use verification-before-completion before completion
8. $speckit-converge
9. inspect final diff
```

### Small bug

```text
1. inspect the real code path
2. systematic-debugging if cause is not established
3. reproduce with a focused failing test where useful
4. minimal fix
5. focused verification
6. final diff review
```

No Spec Kit feature lifecycle is required merely because Spec Kit is installed.

### Large ambiguous feature

```text
1. $speckit-specify
2. $speckit-clarify
3. $speckit-plan
4. $speckit-checklist      # when the risk warrants it
5. $speckit-tasks
6. $speckit-analyze
7. implement bounded task groups
8. Superpowers TDD/debug/review/verification as applicable
9. $speckit-converge
10. repeat implement/converge only for real remaining gaps
```

If one feature is still too large for a stable context, split it into smaller independently specified features rather than continually expanding one session.

---

## 15. Rollout plan

### Phase 1 — Spec Kit only

Install Spec Kit in one active repository.

Use it for one meaningful feature.

Validate:

- artifacts are useful
- task boundaries make sense
- context consumption is acceptable
- repository workflow is not disrupted

### Phase 2 — Add Superpowers

Install Superpowers in both Codex profiles, or use the shared native-skill path; verify each host/profile that will use it.

Initially use only:

```text
test-driven-development
systematic-debugging
verification-before-completion
review skills
```

Do not enable a second planning lifecycle.

### Phase 3 — Add the global integration block

Once behavior is verified in Codex/VS Code, add the short **Structured delivery** section to `llm/codex/__AGENTS.md` and propagate it to both Codex profiles through the corrected policy installation path.

Do not encode assumptions about a skill/plugin being available until you have verified discovery in the actual VS Code Codex host.

### Phase 4 — Measure

Use `token-profiler codex` or `token-profiler codex-work` for several real features.

Look especially for:

- repeated specification text
- repeated plan text
- large framework instructions
- repeated test/build logs
- unnecessary full-file reads
- compactions triggered earlier than before

### Phase 5 — Consider advanced orchestration only if needed

Only after observing a concrete deficiency should you consider:

- Spec Kit Git extension
- Superpowers worktree orchestration
- Superpowers subagent plan execution
- community Spec Kit ↔ Superpowers bridge extensions

---

## 16. Final recommended configuration

For your workflow, the target state is:

```text
llm/codex/__AGENTS.md
    → ~/.codex/AGENTS.md and ~/.codex-work/AGENTS.md
    ├── Build less / Ponytail
    ├── Retrieval: Serena / Context7
    ├── Structured delivery: Spec Kit + Superpowers   ← small addition
    ├── Shell output: RTK / Headroom
    └── Finish / validation

llm/claude/__AGENTS.md
    → ~/.claude/CLAUDE.md and ~/.claude-work/CLAUDE.md
    └── Structured delivery: Spec Kit + Superpowers

~/.codex/ and ~/.codex-work/
    ├── config.toml                                   ← MCPs, plugins, Headroom
    └── hooks.json                                    ← RTK, Serena, version guard, context safeguards

~/.agents/skills/
    ├── pitstop/                                      ← existing checkpoint resume skill
    └── superpowers/                                  ← only for the native-skill option

Superpowers plugin                                   ← alternative, installed in each Codex profile

project/
    ├── .agents/skills/speckit-*/                     ← project-local Spec Kit integration
    ├── .specify/
    ├── specs/<feature>/
    │   ├── spec.md
    │   ├── plan.md
    │   └── tasks.md
    └── code
```

The policy arrows match the installer and smoke-test source paths in §1. Both agent policies include structured delivery routing for Spec Kit and Superpowers.

Operationally:

```text
                  Is this a meaningful feature?
                         /            \
                       no              yes
                       │                │
               normal AGENTS       Spec Kit artifacts
                       │                │
                       └──────┬─────────┘
                              ▼
                       implementation
                              │
                    applicable Superpowers
                              │
               TDD / debug / verify / review
                              │
                              ▼
                      narrow validation
                              │
                              ▼
                        final diff
```

This gives you structured, resumable feature state without forcing every coding task through a heavyweight lifecycle and without paying for two parallel planning systems.

---

## Sources / validation scope

Local architecture alignment was checked on October 12, 2026 against `llm/ai-install.sh`, `llm/agent_config.py`, both agent policy sources, `llm/codex/codex-hooks.json`, `llm/idle_compact.py`, the pitstop skill/command, `llm/smoke-test.sh`, and `llm/token-profiler/README.md`. Executable configuration takes precedence where `README.md` or `llm/TOOLCHAIN.md` still describe the old shared policy source.

OpenAI's instruction and skill discovery documentation was checked for profile precedence and shared/repository skill locations. Superpowers/Spec Kit installation, version-specific commands, plugin availability, and discovery remain adoption checks; this documentation review did not install either tool or run the installer/smoke test.

Upstream adoption references:

- https://github.com/obra/superpowers
- https://github.com/obra/superpowers/blob/main/docs/README.codex.md
- https://github.com/github/spec-kit
- https://github.github.io/spec-kit/
- https://github.github.io/spec-kit/reference/integrations.html
- https://github.github.io/spec-kit/guides/existing-projects.html
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/build-skills
- https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra
