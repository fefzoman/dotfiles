# Idle Compaction Matrix: Claude Code × Codex

> Behavior of `llm/idle_compact.py` as of `ff7f51e`. Design notes and history: `llm/TOOLCHAIN.md` → Idle compaction.

## 1. Characteristics

**Legend:** ✓ Supported · △ Partial · — Not supported

| Aspect | Claude Code | Codex |
|---|---|---|
| **Goal** | Avoid a full cache rewrite (2× input price) when returning after the prompt cache expired | Same |
| **Token floor** | Any context > 0 | Any context > 0 |
| **Cache TTL source** | Latest call's `cache_creation`: 1h or 5m, default 1h | Fixed 30 min (GPT-5.6+ documented minimum) |
| **Checkpoint fires at** | 0.9 × TTL after last call: 54 min (1h) / 4.5 min (5m) | 27 min after last token-usage event |
| **Arm hook** | `Stop`, `async: true`, timeout 4000 s | `Stop`, `async: true`, timeout 11000 |
| **Cancelled by** | New message or newer arm token | Same |
| **Steps aside for native feature** | Yes, when `tengu_sunny_locket.mode == "compact"` | — No equivalent |
| **Wakes the session / model call** | — No | — No |
| **Renews the cache while idle** | — No | — No |
| **Checkpoint content** | First request, latest reply, latest request (≤4K chars each), digest, redacted transcript | Same |
| **Notice when saved** | — None (async output would reach the model, not the user) | △ `systemMessage` "Idle checkpoint saved…" |
| **Guard hook** | `UserPromptSubmit` `guard` | `UserPromptSubmit` `guard --client codex` |
| **Guard fires after** | Gap ≥ TTL (1h or 5m) | Gap ≥ 30 min |
| **Guard, checkpoint ready** | Blocks first prompt once; shows expiry age, rebuild size, checkpoint time; repeats prompt | Blocks first prompt once; shows size; repeats prompt |
| **Guard, no or stale checkpoint** | — Silent | ✓ Non-blocking `/compact` suggestion |
| **Staleness check** | Newer prompt than digest's `last_prompt` | Same |
| **Resume entry point** | `/pitstop` command (`claude/pitstop.md`) | `$pitstop` skill (`codex/pitstop/SKILL.md`) |
| **Same-window handoff** | `/pitstop` → `/clear`; `SessionStart` `clear` loads it within 10 min | `$pitstop` → `/clear`; same |
| **Resume protocol** | State goal + next step, ask to confirm | State goal + next step, no confirm |
| **Detail lookup** | `idle_compact.py turn <session> T<n>`, `search "<words>"` | Same |
| **Storage** | `~/.local/state/idle-compact/`, sessions 7 d, checkpoints 30 d | Same |
| **Kill switch** | `IDLE_COMPACT=off` | Same |

## 2. One idle period

| Time after last call | Claude (1h cache) | Claude (5m cache) | Codex |
|---|---|---|---|
| 0 | `arm` sleeps | `arm` sleeps | `arm` sleeps |
| 0.9 × TTL | Checkpoint at 54 min | Checkpoint at 4.5 min | Checkpoint at 27 min |
| ≥ TTL, next prompt | Guard blocks once (60 min+) | Guard blocks once (5 min+) | Guard blocks once (30 min+) |
| User choice | `/pitstop` + `/clear`, or resend to keep full session | Same | Same |

## 3. Drawbacks

| # | Drawback | Affects | Impact |
|---|---|---|---|
| 1 | **Disabled on this machine.** `arm` skips Claude when the native idle flag is `compact`, which it is; the native compactor did not run on the observed sessions either | Claude | No checkpoint, no guard, full rebuild on every cold resume |
| 2 | **Silent guard without a checkpoint.** Codex falls back to a `/compact` hint; Claude says nothing. Breaks the `llm/` feature-parity rule | Claude | Cold resume with no warning at all |
| 3 | **Excerpts, not a summary.** First request, latest reply and latest request only; no decisions, dead ends or constraints. Long sessions drift far from the first request | Both | Fresh chat may redo dead ends or miss constraints; relies on `turn`/`search` |
| 4 | **Stale resume wording.** `PROTOCOL` still says "Treat Decisions and Dead ends as settled", but no checkpoint has those sections now | Both | Instruction refers to content that does not exist |
| 5 | **No cache renewal.** The old wake turn kept the session warm until ~1.9 × TTL; now the cache expires at 1 × TTL | Claude | Resending after any gap ≥ TTL pays the full rebuild |
| 6 | **No floor.** Tiny sessions get a blocking guard although rebuilding them is cheap | Both | Extra round trip to save little |
| 7 | **5-minute cache is noisy.** Checkpoint every 4.5 min idle and a blocked prompt after every 5-min pause (API key or usage overage) | Claude | Frequent interruptions; frequent full-transcript rewrites on disk |
| 8 | **Assumed TTL.** Fixed 30 min with no per-session expiry signal; the real cache may live longer, or shorter on older models | Codex | Guard may block while the cache is still warm |
| 9 | **Wrong session on fresh-chat `/pitstop`.** Without a handoff, `resume` takes the newest valid checkpoint in the project | Both | Parallel sessions in one repo can load each other's checkpoint |
| 10 | **Background worker dies with the session.** Codex documents cancellation on exit; Claude async hooks behave the same way, unverified | Codex (Claude likely) | Closing the window before 0.9 × TTL leaves no checkpoint |
| 11 | **10-minute handoff window.** `/clear` must follow `/pitstop` within 10 min | Both | Late `/clear` starts an empty session |
| 12 | **Regex-only redaction.** Covers common key, token and password formats | Both | Unusual secrets can land in `transcript.md` (mode 0700 directory) |
| 13 | **No save notice on Claude.** The user learns a checkpoint exists only from the guard | Claude | Cannot choose a fresh chat proactively before returning |
