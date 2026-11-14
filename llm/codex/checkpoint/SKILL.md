---
name: checkpoint
description: Write a checkpoint of this session now so $pitstop can continue from it in a new chat. Use when the user asks for checkpoint or manual compaction.
argument-hint: "[focus <next-session text>]"
---

Write the manual checkpoint exactly as the hook context requests, without running commands.
Bare `$checkpoint` saves the normal handoff. `$checkpoint focus <text>` uses all text after `focus` as the next session's focus and saves a separate `focus_` checkpoint. Focus never relaxes constraints or grants authorization.
