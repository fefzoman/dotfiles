# Terminal Workflow Keybindings

This cheat sheet covers the main keybindings for your current setup:

- Neovim
- Neovim plugins: Telescope, Neo-tree, LazyGit
- tmux

Your Neovim leader key is:

```text
Space
```

So `<leader>e` means: press `Space`, then press `e`.

---

## Neovim: Basic Editing

| Keybinding | Action |
|---|---|
| `i` | Enter insert mode |
| `Esc` | Return to normal mode |
| `:w` | Save file |
| `:q` | Quit |
| `:wq` | Save and quit |
| `:q!` | Quit without saving |
| `u` | Undo |
| `Ctrl + r` | Redo |
| `dd` | Delete current line |
| `yy` | Copy current line |
| `p` | Paste after cursor |
| `P` | Paste before cursor |
| `/text` | Search for `text` |
| `n` | Next search result |
| `N` | Previous search result |
| `gg` | Go to top of file |
| `G` | Go to bottom of file |
| `:number` | Go to line number |

---

## Neovim: Movement

| Keybinding | Action |
|---|---|
| `h` | Move left |
| `j` | Move down |
| `k` | Move up |
| `l` | Move right |
| `w` | Move to next word |
| `b` | Move to previous word |
| `0` | Move to start of line |
| `$` | Move to end of line |
| `%` | Jump to matching bracket |
| `Ctrl + d` | Move half-page down |
| `Ctrl + u` | Move half-page up |

---

## Neovim: Windows and Splits

| Keybinding / Command | Action |
|---|---|
| `:split` | Open horizontal split |
| `:vsplit` | Open vertical split |
| `Ctrl + w`, then `h` | Move to left split |
| `Ctrl + w`, then `j` | Move to lower split |
| `Ctrl + w`, then `k` | Move to upper split |
| `Ctrl + w`, then `l` | Move to right split |
| `Ctrl + w`, then `q` | Close current split |

---

## Telescope

Telescope is used for fuzzy finding files, searching text, and jumping around your project.

| Keybinding | Action |
|---|---|
| `Space + ff` | Find files |
| `Space + fg` | Search text in project |
| `Space + fb` | Find open buffers |
| `Space + fh` | Search help pages |

Useful Telescope commands:

```vim
:Telescope find_files
:Telescope live_grep
:Telescope buffers
:Telescope help_tags
```

Inside Telescope:

| Keybinding | Action |
|---|---|
| `Ctrl + n` | Move selection down |
| `Ctrl + p` | Move selection up |
| `Enter` | Open selected result |
| `Esc` | Close Telescope |
| `Ctrl + x` | Open result in horizontal split |
| `Ctrl + v` | Open result in vertical split |
| `Ctrl + t` | Open result in new tab |

---

## Neo-tree

Neo-tree is your file explorer sidebar.

| Keybinding / Command | Action |
|---|---|
| `Space + e` | Toggle Neo-tree |
| `:Neotree` | Open Neo-tree |
| `:Neotree toggle` | Toggle Neo-tree |
| `:Neotree reveal` | Reveal current file in tree |
| `:Neotree close` | Close Neo-tree |

Inside Neo-tree:

| Keybinding | Action |
|---|---|
| `Enter` | Open file or folder |
| `a` | Add file or folder |
| `d` | Delete file or folder |
| `r` | Rename file or folder |
| `m` | Move file or folder |
| `c` | Copy file or folder |
| `q` | Close Neo-tree |
| `?` | Show Neo-tree help |

---

## LazyGit

LazyGit is a terminal Git UI opened from inside Neovim.

| Keybinding / Command | Action |
|---|---|
| `Space + lg` | Open LazyGit |
| `:LazyGit` | Open LazyGit |

Common LazyGit controls:

| Keybinding | Action |
|---|---|
| Arrow keys / `h j k l` | Move around panels |
| `Space` | Stage / unstage file |
| `c` | Commit |
| `P` | Push |
| `p` | Pull |
| `b` | Branches |
| `q` | Quit LazyGit |
| `?` | Show LazyGit help |

---

## tmux

Your tmux prefix key is the default:

```text
Ctrl + b
```

For tmux shortcuts, press `Ctrl + b`, release, then press the next key.

---

## tmux: Sessions

| Keybinding / Command | Action |
|---|---|
| `tmux` | Start new tmux session |
| `tmux new -s main` | Start session named `main` |
| `tmux attach -t main` | Attach to session named `main` |
| `tmux new-session -A -s main` | Attach to `main`, or create it if missing |
| `Ctrl + b`, then `d` | Detach from tmux session |
| `tmux ls` | List tmux sessions |

---

## tmux: Windows

tmux windows work like terminal tabs.

| Keybinding | Action |
|---|---|
| `Ctrl + b`, then `c` | Create new window |
| `Ctrl + b`, then `n` | Next window |
| `Ctrl + b`, then `p` | Previous window |
| `Ctrl + b`, then `1` | Go to window 1 |
| `Ctrl + b`, then `2` | Go to window 2 |
| `Ctrl + b`, then `,` | Rename current window |
| `Ctrl + b`, then `&` | Close current window |

Your config starts window numbering at `1`.

---

## tmux: Panes

Your custom split bindings are:

| Keybinding | Action |
|---|---|
| `Ctrl + b`, then `,` | Vertical split: left/right |
| `Ctrl + b`, then `.` | Horizontal split: top/bottom |

Default tmux pane controls:

| Keybinding | Action |
|---|---|
| `Ctrl + b`, then `h` | Move to left pane |
| `Ctrl + b`, then `j` | Move to lower pane |
| `Ctrl + b`, then `k` | Move to upper pane |
| `Ctrl + b`, then `l` | Move to right pane |
| `Ctrl + b`, then `x` | Kill current pane |
| `Ctrl + b`, then `z` | Zoom current pane |
| `Ctrl + b`, then `{` | Move pane left |
| `Ctrl + b`, then `}` | Move pane right |

Note: pane movement with `h/j/k/l` may require additional tmux bindings depending on your tmux version/config. Mouse support is enabled in your config, so you can also click panes.

---

## tmux: Copy Mode

| Keybinding | Action |
|---|---|
| `Ctrl + b`, then `[` | Enter copy mode |
| Arrow keys / `h j k l` | Move around |
| `q` | Exit copy mode |

---

## Quick Daily Workflow

```text
Open Alacritty
→ tmux starts automatically
→ open project folder
→ run nvim
→ Space + e      open file tree
→ Space + ff     find file
→ Space + fg     search text
→ Space + lg     manage Git
→ Ctrl + b, c    new tmux window
→ Ctrl + b, ,    vertical split
→ Ctrl + b, .    horizontal split
```
