# Dotfiles

macOS terminal setup for Bash, Oh My Bash, Alacritty, tmux, Neovim, Python,
Terraform, Kubernetes, and common CLI tools.

## Install

```bash
chmod +x ./activate.sh
./activate.sh
```

Run without confirmation prompts:

```bash
./activate.sh auto-approve
```

`auto-approve` makes package managers non-interactive. It cannot bypass
password authentication; privileged `sudo` or `chsh` steps are skipped with a
warning if non-interactive administrator access is unavailable.

Run the stages separately when debugging:

```bash
bash ./basic-install.sh
bash ./reset-to-bash-ohmybash.sh
```

Restart Alacritty after installation. Existing tmux shells may also need to be
restarted before they load the new Bash configuration.

## Installed Tools

| Area | Tools |
|---|---|
| Shell and terminal | latest Homebrew Bash, Oh My Bash, Alacritty, tmux, JetBrainsMono Nerd Font |
| CLI | Git, curl, btop, Codex, LazyGit, ripgrep, fd |
| Infrastructure | kubectl, Terraform |
| Editor | Neovim, vim-plug, Telescope, Neo-tree, vim-airline, LazyGit integration |
| Infrastructure editing | YAML, Kubernetes, Helm, and Terraform plugins |
| Language servers | BasedPyright (Python), clangd (C/C++), rust-analyzer (Rust) |

Homebrew tap trust checks are disabled during setup with
`HOMEBREW_NO_REQUIRE_TAP_TRUST=1`.

## Python

The installer targets Python 3.13 and creates these commands in `~/.local/bin`:

```text
python  python3  pip  pip3
```

`pip` installs globally with `break-system-packages = true`. Other pyenv Python
versions and Homebrew Python formulae are removed when safe; Homebrew versions
required by installed packages are retained. Set `FORCE_REMOVE_PYTHON=1` to
force their removal despite dependencies.

## Generated Configuration

| Path | Purpose |
|---|---|
| `~/.bashrc` | Oh My Bash, aliases, completions, terminal variables, word navigation |
| `~/.bash_profile` | Loads `~/.bashrc` for login shells |
| `~/.oh-my-bash/custom/themes/font/font.theme.sh` | Two-line prompt with clock, host, path, Git branch, and status arrow |
| `~/.config/alacritty/alacritty.toml` | Gruvbox theme, Thin output, Medium command input, automatic tmux session |
| `~/.config/nvim/init.vim` | Plugins, keybindings, file types, and language servers |
| `~/.tmux.conf` | Top status bar, mouse support, pane/window/session bindings |

Existing Alacritty, Neovim, and tmux files receive timestamped `.bak.*` copies.
Shell files and frameworks replaced by the Bash reset are moved to:

```text
~/.shell-reset-backup/<timestamp>/
```

## Shell Shortcuts

| Shortcut | Command |
|---|---|
| `k` | `kubectl` |
| `tf` | `terraform` |
| `v` | `nvim` |
| `term`, `terminal`, `alac` | Open Alacritty |

Oh My Bash completions are enabled for AWS CLI, Terraform, kubectl, Helm,
Minikube, pip, pip3, and uv. On Linux, `pbcopy` maps to `wl-copy`, `xclip`, or
`xsel` when available.

See [terminal_keybindings.md](./terminal_keybindings.md) for Neovim, LSP, tmux,
and shell controls.
