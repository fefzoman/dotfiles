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
Codex, Claude Code, Fabric, RTK, Headroom, Ponytail, Serena, Context7, the token
profiler, and AI profile shell commands. It configures every applicable tool
for personal and work Codex/Claude profiles and installs `llm/__AGENTS.md`
globally for all four. When executed it installs the tools; when sourced it
only loads the AI environment, functions, and aliases. `activate.sh` runs all
three stages in dependency order.

Restart Alacritty after installation. Existing tmux shells may also need to be
restarted before they load the new Bash configuration.

The installer reads the account login shell from macOS Directory Service or
the Linux passwd database. It verifies the result after `chsh` and stops before
resetting existing shell files when the switch to Bash fails. Log out and back
in after a successful shell change; `$SHELL` is not refreshed in the current
login session. Alacritty's tmux panes use the installed Bash even if `$SHELL`
is stale.

## Installed Tools

The commands below are installed or configured by this repository. AWS CLI,
Helm, and Minikube receive shell completions when already present, but this
repository does not install them.

### Shell and Terminal

| Tool | Purpose | Common commands and examples |
|---|---|---|
| Bash | Login shell and command interpreter; macOS uses the latest Homebrew Bash | `bash --version`, `source ~/.bashrc`, `history`, `type COMMAND` |
| Oh My Bash | Bash themes, aliases, and completions; background update checks are disabled to avoid stale locks in concurrent tmux shells | `source ~/.bashrc` reloads it; rerun `./activate.sh` to refresh it |
| Alacritty | GPU-accelerated terminal that automatically attaches to tmux session `main` | `alacritty`, `alacritty --version`; aliases: `term`, `terminal`, `alac` |
| tmux | Persistent terminal sessions, windows, and panes | `tmux new -s NAME`, `tmux ls`, `tmux attach -t NAME`, `tmux kill-session -t NAME` |
| JetBrainsMono Nerd Font | Terminal text and icons used by the prompt, tmux, and Neovim | Select `JetBrainsMono Nerd Font`; Alacritty is configured automatically |

See [terminal_keybindings.md](./terminal_keybindings.md) for all configured
tmux, shell, and Neovim keybindings.

### Core CLI

| Tool | Purpose | Common commands and examples |
|---|---|---|
| Git | Source control | `git status`, `git diff`, `git log --oneline`, `git add FILE`, `git commit`, `git pull --rebase`, `git push` |
| curl | HTTP requests and downloads | `curl -I URL`, `curl -fsSL URL`, `curl -o FILE URL` |
| wget | Recursive or resumable downloads; installed directly on Linux and by the shell reset where available | `wget URL`, `wget -c URL`, `wget -O FILE URL` |
| btop | Interactive CPU, memory, process, disk, and network monitor | `btop`; press `q` to quit and `?` for help |
| LazyGit | Interactive Git interface | `lazygit`; in Neovim use `Space lg` |
| ripgrep (`rg`) | Fast recursive text search that respects `.gitignore` | `rg PATTERN`, `rg PATTERN PATH`, `rg -g '*.py' PATTERN`, `rg --files` |
| fd | Fast file and directory finder | `fd NAME`, `fd -e py`, `fd -t d NAME`; Linux maps `fd` to `fdfind` |
| broot | Interactive tree navigation with Git status | `broot`, `broot PATH`; use `br` to change the parent shell's directory on exit |
| fzf | Fuzzy selection from files, history, or piped text | `fzf`, `fd -t f \| fzf`, `git branch --format='%(refname:short)' \| fzf` |
| Navi | Interactive command cheatsheets backed by TLDR pages | `navi`, `navi --tldr kubectl`, `navi --tldr terraform` |
| TLDR | Short, example-oriented command documentation; the npm client is used on both platforms because Navi requires its `--markdown` output | `tldr tar`, `tldr kubectl`, `tldr --update` |

### Infrastructure

| Tool | Purpose | Common commands and examples |
|---|---|---|
| kubectl | Inspect and manage Kubernetes clusters | `kubectl config current-context`, `kubectl get pods -A`, `kubectl describe pod POD`, `kubectl logs -f POD`, `kubectl apply -f FILE`; alias: `k` |
| Terraform | Provision and manage infrastructure as code | `terraform fmt -recursive`, `terraform init`, `terraform validate`, `terraform plan`, `terraform apply`, `terraform output`; alias: `tf` |

### Runtimes and Build Tools

| Tool | Purpose | Common commands and examples |
|---|---|---|
| Homebrew | Package manager bootstrapped and updated on macOS | `brew update`, `brew search NAME`, `brew install FORMULA`, `brew upgrade`, `brew list` |
| Python 3.13 | Default Python runtime exposed as both `python` and `python3` | `python --version`, `python SCRIPT.py`, `python -m venv .venv`, `python -m unittest` |
| pip | Global Python package installer for the managed Python 3.13 runtime | `pip list`, `pip show PACKAGE`, `pip install PACKAGE`, `pip install -U PACKAGE` |
| uv | Python runtime and isolated tool manager used by the installer | `uv python list`, `uv python install 3.13`, `uv tool list`, `uv tool run TOOL` |
| Node.js | JavaScript runtime; Linux installs current Node 22 LTS | `node --version`, `node FILE.js`, `node -e 'console.log("hello")'` |
| npm / npx / Corepack | JavaScript packages, one-off package execution, and package-manager shims | `npm install`, `npm run SCRIPT`, `npx PACKAGE`, `corepack enable` |
| LLVM/Clang | C and C++ compiler toolchain on macOS | `clang main.c -Wall -Wextra -o app`, `clang++ main.cpp -Wall -Wextra -std=c++20 -o app` |
| build-essential | GCC, G++, Make, and standard build files on Debian/Ubuntu | `gcc main.c -Wall -Wextra -o app`, `g++ main.cpp -Wall -Wextra -std=c++20 -o app`, `make` |
| tree-sitter CLI | Parse and inspect syntax trees; also supports Neovim parser development | `tree-sitter --version`, `tree-sitter parse FILE`, `tree-sitter highlight FILE` |

Compile and run a single source file with:

```bash
clang main.c -Wall -Wextra -o main && ./main
clang++ main.cpp -Wall -Wextra -std=c++20 -o main && ./main
```

On Debian or Ubuntu, use `gcc` and `g++` in place of `clang` and `clang++`.

### Editor and Language Intelligence

| Tool | Purpose | Common commands and examples |
|---|---|---|
| Neovim | Terminal editor configured for navigation, Git, completion, syntax parsing, and LSP | `nvim FILE`, `nvim .`; alias: `v`; inside Neovim: `:checkhealth`, `:PlugUpdate`, `:TSUpdate` |
| vim-plug | Neovim plugin manager | `:PlugInstall`, `:PlugUpdate`, `:PlugClean`, `:PlugStatus` |
| BasedPyright | Python type checker and language server | `basedpyright .`, `basedpyright FILE.py`; starts automatically for Python buffers |
| clangd | C and C++ language server with background indexing and clang-tidy | `clangd --version`, `clangd --check=FILE`; starts automatically for C/C++ buffers |

#### Neovim Plugins

| Plugin | Purpose | Common command, key, or behavior |
|---|---|---|
| vim-airline | Status line and tab information | Enabled automatically |
| vim-colors-violet | Editor color scheme | `:colorscheme violet` |
| vim-devicons | File icons for Vim-style plugins | Enabled automatically; requires the Nerd Font |
| plenary.nvim | Shared Lua utilities required by Telescope and other plugins | Support dependency; no direct command |
| nvim-lspconfig | Connects BasedPyright and clangd to Neovim's LSP client | `:checkhealth vim.lsp`; use `gd`, `gr`, `K`, `Space rn`, `Space ca` |
| Telescope | Fuzzy file, text, buffer, and help search | `Space ff`, `Space fg`, `Space fb`, `Space fh`; command: `:Telescope` |
| lazygit.nvim | Opens LazyGit inside Neovim | `Space lg` or `:LazyGit` |
| nui.nvim | UI components required by Neo-tree | Support dependency; no direct command |
| nvim-web-devicons | File icons for Lua plugins | Enabled automatically; requires the Nerd Font |
| Neo-tree | File explorer | `Space e`, `:Neotree reveal`, `:Neotree close` |
| vim-yaml | YAML syntax and indentation support | Opens `*.yaml` and `*.yml` automatically |
| vim-kubernetes | Kubernetes resource syntax support | Opens Kubernetes YAML automatically |
| vim-helm | Helm template syntax support | Opens Helm templates automatically |
| vim-terraform | Terraform/HCL syntax, alignment, and format-on-save | `:TerraformFmt`; `*.tf`, `*.tfvars`, and `*.hcl` are detected automatically |
| mini.pairs | Inserts matching brackets and quotes | Type `(`, `[`, `{`, `"`, or `'` in insert mode |
| mini.surround | Adds, removes, and replaces surrounding characters | `sa`, `sd`, `sr`; use `:help MiniSurround` |
| indent-blankline.nvim | Displays indentation guides | Enabled automatically |
| nvim-treesitter | Syntax-aware parsing and highlighting for configured languages | `:TSUpdate`, `:checkhealth nvim-treesitter` |

Treesitter parsers are installed for Bash, C, C++, HCL/Terraform, Lua,
Python, Vim, Vimdoc, and YAML.

### AI Tooling

| Tool | Purpose | Common commands and examples |
|---|---|---|
| Codex | Coding agent with shell, repository, MCP, plugin, and current-environment access | `codex`, `codex-work`, `codex exec 'PROMPT'`, `codex resume`; `?? 'QUESTION'` uses `gpt-6-sol` with medium reasoning |
| Claude Code | Coding agent configured with the same optimization stack | `claude`, `claude-work`, `claude -p 'PROMPT'`, `claude --version` |
| VS Code profile launchers | Open an existing VS Code installation with separate personal or work agent state | `code .`, `code-work .`, `claude-code-work .` |
| Fabric | Pattern-based text transformation through a selected model provider; it does not inherit Codex CLI tools or live environment access | `fabric --setup`, `fabric --listpatterns`, `fabric -p summarize < FILE`, `fabric --stream 'PROMPT'` |
| RTK | Compacts supported shell output before it enters an agent's context | `rtk gain`, `rtk gain --history`, `rtk discover --all --since 7`, `RTK_DISABLED=1 COMMAND` |
| Headroom | Local proxy that compresses and manages Codex/Claude context | `headroom install status`, `headroom install apply`, `headroom install remove` |
| Ponytail | Guides agents toward the smallest correct implementation | Codex: `@ponytail`, `@ponytail-review`; Claude: `/ponytail`, `/ponytail-review` |
| Serena | Semantic repository navigation and symbol-level code operations through MCP | Used automatically by Codex/Claude; verify with `/mcp`; CLI: `serena --help` |
| Context7 | Retrieves current third-party library and API documentation through MCP | Used automatically by Codex/Claude; verify with `/mcp`; CLI: `context7-mcp --help` |
| token-profiler | Local usage, inner-session, context, and optimization reports for all four agent profiles | `token-profiler codex`, `token-profiler codex-work short`, `token-profiler claude current`, `token-profiler codex top --by command` |
| tiktoken | Tokenizer used by token-profiler for diagnostic attribution estimates | `python -c 'import tiktoken; print(tiktoken.get_encoding("o200k_base"))'` |
| LLM smoke test | Verifies commands, profile routing, policies, hooks, plugins, and MCPs without model calls | `bash ./llm/smoke-test.sh`, `bash ./llm/smoke-test.sh --strict` |

### Linux Support Packages

These Debian/Ubuntu packages support installation and desktop integration but
are not primary interactive tools.

| Package | Purpose | Useful command |
|---|---|---|
| ca-certificates | Validates HTTPS certificates used by download tools | `update-ca-certificates` |
| dconf-cli | Desktop configuration support | `dconf dump /`, `dconf read KEY` |
| fontconfig | Discovers and caches installed fonts | `fc-list`, `fc-cache -f` |
| unzip / xz-utils | Extracts ZIP and XZ archives used by installers | `unzip FILE.zip`, `tar -xJf FILE.tar.xz` |
| xclip | X11 clipboard provider used by the `pbcopy` compatibility alias | `printf text \| xclip -selection clipboard` |

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
tool environment. The installer runs it as a persistent launchd/systemd proxy on
port 8787 (`headroom install apply`) and routes all four profiles to it through
their own config, so terminal CLIs and the VS Code extensions share one path:

```text
~/.claude/settings.json, ~/.claude-work/settings.json   env.ANTHROPIC_BASE_URL
~/.codex/config.toml,    ~/.codex-work/config.toml      model_provider = "headroom"
```

The default Claude profile is always used without `CLAUDE_CONFIG_DIR`, because
setting it (even to `~/.claude`) moves user MCPs such as Serena into
`~/.claude/.claude.json`, which the VS Code extension never reads. Headroom's
anonymous beacon is disabled with `HEADROOM_BEACON=off`. Check the proxy with
`headroom install status`; remove it with `headroom install remove`.

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
removal despite dependencies. A broken Homebrew Python falls back to a
uv-managed Python. Linux uses a uv-managed Python and does not
remove distribution-managed Python packages.

## Generated Configuration

| Path | Purpose |
|---|---|
| `~/.bashrc` | Oh My Bash, aliases, completions, terminal variables, word navigation |
| `~/.config/dotfiles/ai-install.sh` | Sourced Codex/Claude profiles, Codex `??` helper, and AI telemetry settings |
| `~/.codex/AGENTS.md`, `~/.codex-work/AGENTS.md` | Global Codex policy installed from `llm/__AGENTS.md` |
| `~/.codex/hooks.json`, `~/.codex-work/hooks.json` | Serena activation/reminder/cleanup and context-warning hooks |
| `~/.claude/CLAUDE.md`, `~/.claude-work/CLAUDE.md` | Global Claude policy installed from `llm/__AGENTS.md` |
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
| `?? [QUESTION]` | Answer through Codex using `gpt-6-sol` with medium reasoning |

Oh My Bash completions are enabled for AWS CLI, Terraform, kubectl, Helm,
Minikube, pip, pip3, and uv. On Linux, `pbcopy` maps to `wl-copy`, `xclip`, or
`xsel` when available.

Run `navi`, `navi --tldr <command>`, or `tldr <command>` for community examples.
The installer clones and updates
[denisidoro/navi-tldr-pages](https://github.com/denisidoro/navi-tldr-pages) in
Navi's platform-specific cheatsheet directory.

See [terminal_keybindings.md](./terminal_keybindings.md) for Neovim, LSP, tmux,
and shell controls.
