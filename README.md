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
bash ./llm/ai-install.sh
```

Run the read-only LLM toolchain smoke test separately:

```bash
bash ./llm/smoke-test.sh          # all required profile integrations
bash ./llm/smoke-test.sh --strict # warnings also fail the test
```

The smoke test makes no model or API requests. `llm/ai-install.sh` runs the
non-strict test automatically after installation.

`basic-install.sh` owns general machine tooling, while `llm/ai-install.sh` owns
Codex, Claude Code, RTK, Headroom, Ponytail, Serena, Context7, the token
profiler, and AI profile shell commands. It configures every applicable tool
for personal and work Codex/Claude profiles and installs `llm/AGENTS.md`
globally for all four. When executed it installs the tools; when sourced it
only loads the AI environment, functions, and aliases. `activate.sh` runs all
three stages in dependency order.

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
| CLI | Git, curl, btop, Codex, Claude Code, Headroom, Ponytail, Serena, Context7, token profiler, RTK, LazyGit, ripgrep, fd, broot (`br`) |
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
Neovim, Node 22 LTS, kubectl, Terraform, LazyGit, Codex, Claude Code, Serena,
Context7, Treesitter CLI, Python 3.13, and the JetBrainsMono Nerd Font are
installed under `~/.local`, so no Linuxbrew is required.

## RTK

[RTK](https://github.com/rtk-ai/rtk) filters noisy shell-command output before
it reaches Codex. Setup disables RTK telemetry, leaves custom filters untrusted,
and installs RTK awareness instructions into both profiles:

```text
~/.codex/{AGENTS.md,RTK.md}
~/.codex-work/{AGENTS.md,RTK.md}
```

`codex` and `code` default to `~/.codex`; `codex-work` and `code-work` use
`~/.codex-work`. Claude and Claude Work receive native RTK hooks in
`~/.claude` and `~/.claude-work`. Restart the clients after activation so they
load the instructions and hooks. Stable RTK currently integrates with Codex
through instructions rather than a programmatic command hook. Useful commands:

```bash
rtk gain                         # savings dashboard
rtk gain --history               # recent rewritten commands
rtk discover --all --since 7     # missed filtering opportunities
rtk gain --all --format json     # machine-readable savings
```

## Headroom

[Headroom](https://github.com/headroomlabs-ai/headroom) is installed with its
Codex and Claude proxies and code-compression dependencies in an isolated `uv`
tool environment. All four profiles are routed through a session-local
Headroom proxy:

```bash
codex             # Headroom + ~/.codex
codex-work        # Headroom + ~/.codex-work
claude            # Headroom + ~/.claude
claude-work       # Headroom + ~/.claude-work
```

The wrappers respect `CODEX_HOME` and `CLAUDE_CONFIG_DIR`, keep RTK enabled,
and avoid installing a second Serena setup. If `headroom` is unavailable, each
shell function falls back to its CLI directly. Headroom's anonymous beacon is
disabled with `HEADROOM_BEACON=off`. Run `command codex` or `command claude` to
intentionally bypass Headroom.

## Ponytail

[Ponytail](https://github.com/DietrichGebert/ponytail) is installed as a plugin
in all personal and work Codex/Claude profiles. Its lifecycle hooks and skills
load in every CLI while model traffic still routes through Headroom. Node.js is
installed because Ponytail's hooks require it.

After installation, start each profile, review Ponytail's hooks, then start a
new thread. Hook trust is intentionally not granted by `auto-approve`.
Ponytail defaults to `full`; Codex uses `@ponytail` commands and Claude uses
`/ponytail` commands.

## Serena and Context7

Serena and Context7 are installed locally and registered as user-level MCP
servers in `~/.codex`, `~/.codex-work`, `~/.claude`, and `~/.claude-work`.
Serena starts with the client-specific context and detects the project from the
working directory. Context7 works anonymously by default; set
`CONTEXT7_API_KEY` for higher limits or private repositories.

## Token Profiler

`token-profiler` is installed from `llm/token-profiler/` into `~/.local/bin`.
The first subcommand selects the agent and profile explicitly:

```bash
token-profiler codex                       # ~/.codex, latest full report
token-profiler codex-work short            # ~/.codex-work, compact report
token-profiler claude                      # ~/.claude, latest full report
token-profiler claude-work current --json  # ~/.claude-work, JSON report
token-profiler codex sessions
token-profiler claude session SESSION_ID
token-profiler codex top --by command --sessions 100
```

Codex sessions come from `sessions/` and `archived_sessions/`; Claude Code
transcripts come from `projects/` inside the selected profile, including
companion subagent transcripts in the parent session totals.
Exact telemetry includes input, cache reads, cache creation when available,
output, reasoning when available, model calls, and compactions. Reports also
show exact usage for the latest inner session, where a gap greater than 30
minutes starts a new work period.

Optimization reporting keeps scopes separate: exact cache reuse, estimated RTK
project savings, Headroom's global savings ledger, observed Serena/Context7
activity, and Ponytail activation status. The profiler does not add overlapping
savings or invent a Ponytail savings number. Exact token totals remain
authoritative.

It is local and read-only: it does not modify sessions, call OpenAI or
Anthropic APIs, upload session contents, or execute recorded commands. JSON
reports can contain local paths and command strings and should be treated as
sensitive.

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
| `~/.config/dotfiles/ai-install.sh` | Sourced Codex/Claude profiles, Headroom wrapper, `??`, and AI telemetry settings |
| `~/.codex/AGENTS.md`, `~/.codex-work/AGENTS.md` | Global Codex policy installed from `llm/AGENTS.md` |
| `~/.claude/CLAUDE.md`, `~/.claude-work/CLAUDE.md` | Global Claude policy installed from `llm/AGENTS.md` |
| `~/.bash_profile` | Loads `~/.bashrc` for login shells |
| `~/.oh-my-bash/custom/themes/font/font.theme.sh` | Two-line prompt with clock, host, path, Git branch, and status arrow |
| `~/.config/alacritty/alacritty.toml` | Gruvbox theme, Thin output, Medium command input, narrow beam cursor, automatic tmux session |
| `~/.config/nvim/init.vim` | Plugins, keybindings, narrow insert cursor, file types, and language servers |
| `~/.tmux.conf` | Top status bar, mouse support, pane/window/session bindings |
| `~/.codex/RTK.md`, `~/.codex-work/RTK.md` | Profile-specific RTK instructions imported by Codex policies |
| `~/.claude/RTK.md`, `~/.claude-work/RTK.md` | Profile-specific RTK instructions and native command hooks for Claude |
| `~/.codex/config.toml`, `~/.codex-work/config.toml` | Codex profile settings, MCP servers, and Ponytail registration |
| `~/.claude/settings.json`, `~/.claude-work/settings.json` | Claude hooks and profile settings |
| `~/.claude/.claude.json`, `~/.claude-work/.claude.json` | Claude user-level MCP and plugin registration |

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
| `code [ARGS]` | Open VS Code with `~/.codex` as `CODEX_HOME` |
| `codex [ARGS]` | Run Ponytail-enabled Codex through Headroom with `~/.codex` |
| `codex-work [ARGS]` | Run Ponytail-enabled Codex through Headroom with `~/.codex-work` |
| `code-work [ARGS]` | Open VS Code with the Codex work profile |
| `claude [ARGS]` | Run Ponytail-enabled Claude through Headroom with `~/.claude` |
| `claude-work [ARGS]` | Run Ponytail-enabled Claude through Headroom with `~/.claude-work` |
| `claude-code-work [ARGS]` | Open VS Code with the Claude work profile |

Oh My Bash completions are enabled for AWS CLI, Terraform, kubectl, Helm,
Minikube, pip, pip3, and uv. On Linux, `pbcopy` maps to `wl-copy`, `xclip`, or
`xsel` when available.

See [terminal_keybindings.md](./terminal_keybindings.md) for Neovim, LSP, tmux,
and shell controls.
