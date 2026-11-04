---
description: Continue from an idle checkpoint (pass the session ID printed by the checkpoint message)
argument-hint: "[session]"
allowed-tools: Bash(python3 ~/.config/dotfiles/idle_compact.py:*)
---

!`python3 ~/.config/dotfiles/idle_compact.py resume "$ARGUMENTS"`
