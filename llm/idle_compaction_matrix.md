# Idle Compaction Matrix: Claude Code × Codex

> Behavior of `llm/idle_compact.py` after the drawback fixes. Design notes: `llm/TOOLCHAIN.md` → Idle compaction.

## 1. Characteristics

**Legend:** ✓ Supported · △ Partial · — Not supported

| Aspect | Claude Code | Codex |
|---|---|---|
| **Goal** | Avoid the 2× cache rewrite on a cold resume | Avoid a full uncached resend on a cold resume |
| **Token floor** | 85K (2× a fresh chat's median 42K) | 45K (2× the median 22K) |
| **Cache TTL source** | Latest call's `cache_creation`: 1h or 5m | 30 min documented minimum, plus learned per-model hit rate |
| **Checkpoint fires at** | 0.9 × TTL: 54 min / 4.5 min (0.93 when the native compactor flag is on) | 27 min |
| **Who writes it** | ✓ Same model, headless: `claude -p --resume --fork-session` | ✓ Same model, headless: `codex exec fork --ephemeral` |
| **Context it sees** | Full session; prefix read from cache (measured 52.7K read, 1.9K written) | Full thread; the original prefix is read from cache (measured 12.7K of 12.9K) |
| **Sections** | Goal, Done, Decisions, Dead ends, Current state, Constraints, Next steps, Pointers | Same |
| **Renews the session cache** | ✓ The fork reads the shared prefix; the guard counts the gap from the fork | △ The fork reads the shared prefix; renewal not measured, so the guard counts from the last call |
| **Visible to the user** | — Silent; the guard reports it | Same |
| **Native compactor** | Coexists: fires after it, cancels if it ran | No equivalent |
| **Session closed before firing** | `SessionEnd` saves excerpts (not on `/clear`) | Same |
| **Fallback content** | Excerpts: first request, latest reply, latest request | Same, also when the fork fails |
| **Guard, checkpoint ready** | 1h cache: blocks once, repeats prompt. 5m cache: hint | Blocks once; hint when the model's cache is usually warm |
| **Guard, no or stale checkpoint** | ✓ `/compact` hint | ✓ `/compact` hint, silent when the cache is usually warm |
| **Staleness** | `last_prompt` stored in the checkpoint header | Same |
| **Resume** | `/clear`, then `/pitstop <session>`; bare resume prefers the handoff, then newest | `$pitstop <session>` in a new chat; bare resume prefers the current session, then handoff, then newest |
| **Handoff** | Until the old chat moves on; `/clear` loads nothing by itself | Use New Chat and the explicit session ID; IDE `/clear` text does not reset context |
| **Redaction** | Common key/token formats, JWTs, URL credentials, password assignments | Same |
| **Kill switch** | `IDLE_COMPACT=off` | Same |

## 2. One idle period

| Time after last call | Claude (1h cache) | Claude (5m cache) | Codex |
|---|---|---|---|
| 0 | `arm` sleeps | `arm` sleeps | `arm` sleeps |
| 0.9 × TTL | Fork writes checkpoint | Same at 4.5 min | Fork writes checkpoint at 27 min |
| ≥ TTL after the fork (Claude) or last call (Codex), next prompt | Guard blocks once | Non-blocking hint | Block, or hint if the model's cache is usually warm |
| User choice | `/clear` + `/pitstop <session>`, or resend to keep the full session | Same | New Chat + `$pitstop <session>`, or resend to keep the full session |

## 3. Drawbacks: resolution

| # | Drawback | Fix |
|---|---|---|
| 1 | Disabled when the native flag is on | Never skips; fires at 0.93 so a native compaction that runs wins |
| 2 | Claude guard silent without a checkpoint | Shared `/compact` hint for both clients |
| 3 | Excerpts, not a summary | Model-written sections for both clients |
| 4 | Resume wording named missing sections | Sections are back; wording says "any" for excerpt fallbacks |
| 5 | No cache renewal | Both forks read the shared prefix |
| 6 | No floor | 2× fresh-chat floor per client |
| 7 | 5-minute cache noisy | Non-blocking hint instead of a block |
| 8 | Codex TTL assumed | Learned per-model hit rate turns the block into a hint |
| 9 | `/pitstop` could take another session or invalidate its own checkpoint | Prefer the current Codex session or handoff; explicit session IDs for new chats; resume-only prompts stay fresh |
| 10 | Worker dies with the session | `SessionEnd` saves excerpts for both clients |
| 11 | 10-minute handoff window | Removed; staleness invalidates instead |
| 12 | Narrow redaction | More formats covered |
| 13 | No save notice on Claude | Both clients save silently; the guard reports the checkpoint |

## 4. Remaining limits

| Limit | Affects | Why it stays |
|---|---|---|
| Checkpoint turn appears in the session | Claude | Only an in-session turn reads the warm cache; a headless fork breaks the prefix |
| Close-time checkpoint is excerpts only | Both | No model is running once the session ends |
| Warm-cache learning needs 5 post-gap samples per model | Codex | Starts from blocking until data accumulates |
| Fork cache renewal unmeasured | Codex | Needs a long-gap measurement |
| Close-time transcript may be unavailable | Codex | `SessionEnd` documents nullable `transcript_path`; without a readable file the worker cannot save excerpts ([details](TOOLCHAIN.md#verified-behavior-and-remaining-limits-2026-10-25)) |
| Pattern redaction | Both | Unknown secret formats still pass; directory is 0700 |
