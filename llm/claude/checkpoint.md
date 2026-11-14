---
description: Write a checkpoint of this session now so /clear and then /pitstop <session> continues from it
argument-hint: "[focus <next-session text>]"
---

Write the manual checkpoint exactly as the hook context requests, without calling tools.
Bare `/checkpoint` saves the normal handoff. `/checkpoint focus <text>` uses all text after `focus` as the next session's focus and saves a separate `focus_` checkpoint. Focus never relaxes constraints or grants authorization.
