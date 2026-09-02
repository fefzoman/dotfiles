# Terminal Keybindings

Neovim uses `Space` as `<leader>`. tmux uses `Ctrl+b` as its prefix; press the
prefix, release it, then press the action key.

## Shell

| Keybinding | Action |
|---|---|
| `Ctrl+Left`, `Option+Left` | Move one word backward |
| `Ctrl+Right`, `Option+Right` | Move one word forward |

## Neovim

### Editing and Movement

| Keybinding | Action | Keybinding | Action |
|---|---|---|---|
| `i` | Insert mode | `Esc` | Normal mode |
| `:w` | Save | `:q` | Quit |
| `:wq` | Save and quit | `:q!` | Quit without saving |
| `u` | Undo | `Ctrl+r` | Redo |
| `dd` | Delete line | `yy` | Copy line |
| `p` / `P` | Paste after / before | `/text` | Search |
| `n` / `N` | Next / previous result | `:number` | Go to line |
| `h j k l` | Move left/down/up/right | `w` / `b` | Next / previous word |
| `0` / `$` | Start / end of line | `%` | Matching bracket |
| `gg` / `G` | Top / bottom | `Ctrl+d` / `Ctrl+u` | Half-page down / up |

### Windows

| Keybinding or command | Action |
|---|---|
| `:split` / `:vsplit` | Horizontal / vertical split |
| `Ctrl+w`, then `h j k l` | Move between splits |
| `Ctrl+w`, then `q` | Close current split |

### Language Servers

| Language | Server |
|---|---|
| Python | BasedPyright |
| C and C++ | clangd |
| Rust | rust-analyzer |

The following mappings appear when a language server attaches:

| Keybinding | Action |
|---|---|
| `gd` | Go to definition |
| `gr` | Show references |
| `K` | Show documentation |
| `Space rn` | Rename symbol |
| `Space ca` | Code action |
| `Space f` | Format buffer |
| `[d` / `]d` | Previous / next diagnostic |
| `Ctrl+Space` | Completion in insert mode |
| `:checkhealth vim.lsp` | Check configuration and attached servers |

### Telescope

| Keybinding | Action |
|---|---|
| `Space ff` | Find files |
| `Space fg` | Search project text |
| `Space fb` | Find open buffers |
| `Space fh` | Search help |

Equivalent commands are `:Telescope find_files`, `:Telescope live_grep`,
`:Telescope buffers`, and `:Telescope help_tags`.

| Inside Telescope | Action |
|---|---|
| `Ctrl+n` / `Ctrl+p` | Selection down / up |
| `Enter` / `Esc` | Open / close |
| `Ctrl+x` / `Ctrl+v` / `Ctrl+t` | Open in horizontal split / vertical split / tab |

### Neo-tree

| Keybinding or command | Action |
|---|---|
| `Space e` | Toggle Neo-tree |
| `:Neotree` / `:Neotree toggle` | Open / toggle |
| `:Neotree reveal` / `:Neotree close` | Reveal current file / close |
| `Enter` | Open file or folder |
| `a` / `d` / `r` | Add / delete / rename |
| `m` / `c` | Move / copy |
| `q` / `?` | Close / help |

### LazyGit

Open with `Space lg` or `:LazyGit`.

| Keybinding | Action |
|---|---|
| Arrow keys or `h j k l` | Move between panels |
| `Space` | Stage or unstage |
| `c` | Commit |
| `P` / `p` | Push / pull |
| `b` | Branches |
| `q` / `?` | Quit / help |

## tmux

Alacritty automatically attaches to the `main` session or creates it. Window
and pane numbering starts at `1`, and mouse support is enabled.

### Sessions and Windows

| Command or binding | Action |
|---|---|
| `tmux` | Start a default session |
| `tmux new-session -A -s main` | Attach to or create `main` |
| `tmux new -s NAME` / `tmux attach -t NAME` | Create / attach named session |
| `tmux ls` | List sessions |
| `Ctrl+b d` | Detach |
| `Ctrl+b k` | Kill current session with confirmation |
| `Ctrl+b c` | Create window |
| `Ctrl+b n` / `Ctrl+b p` | Next / previous window |
| `Ctrl+b 1` ... `9` | Select window |
| `Ctrl+b q` | Close current window with confirmation |
| `Ctrl+b :`, then `rename-window NAME` | Rename window (`Ctrl+b ,` is used for splitting) |

`Ctrl+b &` is disabled.

### Panes

| Keybinding | Action |
|---|---|
| `Ctrl+b ,` | Split left/right |
| `Ctrl+b .` | Split top/bottom |
| `Ctrl+b` + arrow | Move to the pane in that direction |
| `Ctrl+b x` | Kill pane |
| `Ctrl+b z` | Toggle pane zoom |
| `Ctrl+b {` / `Ctrl+b }` | Move pane left / right |

### Copy Mode

| Keybinding | Action |
|---|---|
| `Ctrl+b [` | Enter copy mode |
| Arrow keys or `h j k l` | Move |
| `q` | Exit copy mode |

## Daily Workflow

```text
Open Alacritty -> main tmux session starts
cd PROJECT && nvim
Space e   file tree       Space ff  find file
Space fg  search text     Space lg  Git UI
Ctrl+b c  new window      Ctrl+b ,  left/right split
Ctrl+b .  top/bottom split
```
