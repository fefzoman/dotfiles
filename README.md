# Dotfiles

Terminal setup for macOS, Debian, and Ubuntu with Bash, Oh My Bash, Alacritty,
tmux, Neovim, Python, Terraform, Kubernetes, and common CLI tools. Linux
installations support x86-64 and ARM64.

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
clear error if non-interactive administrator access is unavailable. Run
`sudo -v` immediately before activation when administrator access is required.

Run the stages separately when debugging:

```bash
bash ./basic-install.sh
bash ./reset-to-bash-ohmybash.sh
```

Restart Alacritty after installation. Existing tmux shells may also need to be
restarted before they load the new Bash configuration.

The installer reads the account login shell from macOS Directory Service or
the Linux passwd database. It verifies the result after `chsh` and stops before
resetting existing shell files when the switch to Bash fails. Log out and back
in after a successful shell change; `$SHELL` is not refreshed in the current
login session.

## Installed Tools

| Area | Tools |
|---|---|
| Shell and terminal | latest Homebrew Bash, Oh My Bash, Alacritty, tmux, JetBrainsMono Nerd Font |
| CLI | Git, curl, btop, Codex, Codex token profiler, LazyGit, ripgrep, fd |
| Infrastructure | kubectl, Terraform |
| Development | LLVM/Clang, tree-sitter CLI |
| Editor | Neovim, vim-plug, Telescope, Neo-tree, Treesitter, Mini Pairs, Mini Surround, indent guides, vim-airline, LazyGit integration |
| Infrastructure editing | YAML, Kubernetes, Helm, and Terraform plugins |
| Language servers | BasedPyright (Python), clangd (C/C++) |

Homebrew tap trust checks are disabled during setup with
`HOMEBREW_NO_REQUIRE_TAP_TRUST=1`.

On macOS, Alacritty is installed from its pinned official DMG because Homebrew
disabled the unnotarized cask on September 1, 2026. The installer verifies the
release SHA-256 and signature, and refuses to remove Gatekeeper quarantine
attributes. Override both `ALACRITTY_VERSION` and `ALACRITTY_SHA256` together
to install another release.

On Debian and Ubuntu, system dependencies and Alacritty come from APT. Current
Neovim, kubectl, Terraform, LazyGit, Codex, Treesitter CLI, Python 3.13, and the
JetBrainsMono Nerd Font are installed under `~/.local`, so no Linuxbrew is
required.

## Codex Token Profiler

`codex-usage` is installed from `codex-token-profiler/` into `~/.local/bin`.
It reads rollout JSONL files under `$CODEX_HOME/sessions` and
`$CODEX_HOME/archived_sessions`, defaulting to `~/.codex`.

```bash
codex-usage short                         # compact latest-session report
codex-usage current                       # latest session
codex-usage sessions                      # recent sessions
codex-usage session 01a08a70              # UUID prefix or rollout path
codex-usage top --by session              # rank sessions
codex-usage top --by command --sessions 100
codex-usage top --by file --sessions 100
codex-usage current --json                 # machine-readable output
```

Exact telemetry includes cumulative input, cached input, fresh input, output,
reasoning output, model calls, context-window usage, and compactions. Activity,
command, file, tool, instruction, and retained-history attribution is estimated
with the mandatory `tiktoken` dependency and its `o200k_base` encoding; exact
token totals remain authoritative. The profiler installer installs or upgrades
`tiktoken` automatically.

The profiler honors separate Codex profiles:

```bash
CODEX_HOME="$HOME/.codex-work" codex-usage current
alias codex-usage-work='CODEX_HOME="$HOME/.codex-work" codex-usage'
```

It is local and read-only: it does not modify sessions, call OpenAI APIs,
upload rollout contents, or execute commands found in rollouts. JSON reports
can contain local paths and command strings and should be treated as sensitive.

## Python

The installer targets Python 3.13 and creates these commands in `~/.local/bin`:

```text
python  python3  pip  pip3
```

`pip` installs globally into the selected Python 3.13 runtime with
`break-system-packages = true`. On macOS, other pyenv Python versions and
Homebrew Python formulae are removed when safe; Homebrew versions required by
installed packages are retained. Set `FORCE_REMOVE_PYTHON=1` to force their
removal despite dependencies. Linux uses a uv-managed Python and does not
remove distribution-managed Python packages.

## Generated Configuration

| Path | Purpose |
|---|---|
| `~/.bashrc` | Oh My Bash, aliases, completions, terminal variables, word navigation |
| `~/.bash_profile` | Loads `~/.bashrc` for login shells |
| `~/.oh-my-bash/custom/themes/font/font.theme.sh` | Two-line prompt with clock, host, path, Git branch, and status arrow |
| `~/.config/alacritty/alacritty.toml` | Gruvbox theme, Thin output, Medium command input, narrow beam cursor, automatic tmux session |
| `~/.config/nvim/init.vim` | Plugins, keybindings, narrow insert cursor, file types, and language servers |
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
| `codex-work` | Run Codex with `~/.codex-work` as `CODEX_HOME` |
| `code-work [ARGS]` | Open VS Code with the Codex work profile |
| `claude-work` | Run Claude with `~/.claude-work` as its config directory |
| `claude-code-work [ARGS]` | Open VS Code with the Claude work profile |

Oh My Bash completions are enabled for AWS CLI, Terraform, kubectl, Helm,
Minikube, pip, pip3, and uv. On Linux, `pbcopy` maps to `wl-copy`, `xclip`, or
`xsel` when available.

See [terminal_keybindings.md](./terminal_keybindings.md) for Neovim, LSP, tmux,
and shell controls.
