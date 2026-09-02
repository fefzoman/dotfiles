#!/usr/bin/env bash
set -euo pipefail

export HOMEBREW_NO_REQUIRE_TAP_TRUST=1
DOTFILES_AUTO_APPROVE=${DOTFILES_AUTO_APPROVE:-0}

ts="$(date +%Y%m%d%H%M%S)"
BACKUP_DIR="$HOME/.shell-reset-backup/$ts"
mkdir -p "$BACKUP_DIR"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m%s\033[0m\n" "$*"; }

move_to_backup() {
  local source="$1" target="$BACKUP_DIR/${1#"$HOME"/}"
  [[ -e "$source" || -L "$source" ]] || return 0
  mkdir -p "$(dirname "$target")"
  bold "Backing up: $source"
  mv "$source" "$target"
}

have() { command -v "$1" >/dev/null 2>&1; }

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif ! have sudo; then
    warn "sudo is unavailable; skipped: $*"
    return 1
  elif [[ "$DOTFILES_AUTO_APPROVE" == "1" ]]; then
    sudo -n "$@"
  else
    sudo "$@"
  fi
}

install_pkgs() {
  if have apt-get; then
    run_root env DEBIAN_FRONTEND=noninteractive apt-get update -y || true
    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" || true
  elif have dnf; then
    run_root dnf install -y "$@" || true
  elif have pacman; then
    run_root pacman -Sy --noconfirm "$@" || true
  elif have zypper; then
    run_root zypper install -y "$@" || true
  elif have brew; then
    brew install "$@" || true
  else
    warn "No supported package manager; install manually: $*"
  fi
}

latest_stable_bash_path() {
  local brew_bash

  if have brew; then
    brew install bash >/dev/null 2>&1 || true
    brew upgrade bash >/dev/null 2>&1 || true
    brew_bash="$(brew --prefix bash 2>/dev/null || true)"
    if [[ -n "$brew_bash" && -x "${brew_bash}/bin/bash" ]]; then
      printf '%s\n' "${brew_bash}/bin/bash"
      return 0
    fi
  fi

  command -v bash || true
}

ensure_login_shell_registered() {
  local shell_path="$1"

  [[ -f /etc/shells ]] || return 0
  grep -Fxq "$shell_path" /etc/shells 2>/dev/null && return 0

  bold "Registering login shell: $shell_path"
  if [[ -w /etc/shells ]]; then
    printf '%s\n' "$shell_path" >> /etc/shells
  elif ! printf '%s\n' "$shell_path" | run_root tee -a /etc/shells >/dev/null; then
    warn "Cannot update /etc/shells; run: echo '$shell_path' | sudo tee -a /etc/shells"
  fi
}

change_login_shell() {
  local shell_path="$1" login_user="${SUDO_USER:-${USER:-$(id -un)}}"
  if [[ "$DOTFILES_AUTO_APPROVE" == "1" ]]; then
    run_root chsh -s "$shell_path" "$login_user"
  else
    chsh -s "$shell_path"
  fi
}

bold "=== 1) Reset Bash/Zsh customizations (backup + clean start) ==="
for path in \
  .bashrc .bash_profile .bash_login .profile .inputrc .bash_aliases \
  .zshrc .zprofile .zshenv .zlogin .zlogout .oh-my-zsh .zinit .antigen .p10k.zsh \
  .config/starship.toml .oh-my-bash .bash_it; do
  move_to_backup "$HOME/$path"
done

ok "Backups stored in: $BACKUP_DIR"
warn "If you use chezmoi (or similar), it may re-apply old dotfiles after this."

bold $'\n=== 2) Switch login shell to Bash (disable Zsh as default) ==='
BASH_PATH="$(latest_stable_bash_path)"
[[ -n "$BASH_PATH" ]] || { warn "bash not found in PATH."; exit 1; }

ensure_login_shell_registered "$BASH_PATH"

if [[ "${SHELL:-}" != "$BASH_PATH" ]]; then
  if have chsh; then
    bold "Attempting: chsh -s $BASH_PATH"
    if change_login_shell "$BASH_PATH" >/dev/null 2>&1; then
      ok "Login shell set to bash. (You must log out/in for it to fully take effect.)"
    else
      warn "chsh needs authentication or admin permission; run: chsh -s $BASH_PATH"
    fi
  else
    warn "chsh not available. Set your default shell to bash manually."
  fi
else
  ok "Your \$SHELL already points to bash."
fi

bold $'\n=== 3) Install Oh My Bash + enable pure + apply prompt + install Nerd Font + import terminal colors ==='

bold "Installing dependencies (git, curl, wget, dconf-cli if possible)..."
install_pkgs git curl wget dconf-cli

write_two_line_font_theme() {
  local theme_dir="$HOME/.oh-my-bash/custom/themes/font"

  mkdir -p "$theme_dir"

  cat > "$theme_dir/font.theme.sh" <<'EOF'
#! bash oh-my-bash.module
#
# Minimal two-line variant of the built-in font theme.
# Keeps timestamp, user, host, and path on the first line.
# Places only the prompt arrow on its own line.

CLOCK_THEME_PROMPT_PREFIX=''
CLOCK_THEME_PROMPT_SUFFIX=' '
THEME_SHOW_CLOCK=${THEME_SHOW_CLOCK:-"true"}
THEME_CLOCK_COLOR=${THEME_CLOCK_COLOR:-"$_omb_prompt_gray"}
THEME_CLOCK_FORMAT=${THEME_CLOCK_FORMAT:-"%I:%M:%S"}
OMB_PROMPT_VIRTUALENV_FORMAT='(%s) '
OMB_PROMPT_SHOW_PYTHON_VENV=${OMB_PROMPT_SHOW_PYTHON_VENV:=true}

function _omb_theme_git_branch_suffix() {
  local branch

  if ! command -v git >/dev/null 2>&1; then
    return
  fi

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return
  fi

  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || true)"

  if [[ -n "$branch" ]]; then
    printf '%s' "$branch"
  fi
}

function _omb_theme_PROMPT_COMMAND() {
  local RC="$?"
  local hostname="${_omb_prompt_gray}\u@\h"
  local python_venv
  _omb_prompt_get_python_venv python_venv=$_omb_prompt_white$python_venv
  local git_branch
  git_branch="$(_omb_theme_git_branch_suffix)"
  if [[ -n "$git_branch" ]]; then
    git_branch=" \[\e[38;5;240m\] ${git_branch}\[\e[0m\]"
  fi
  local ret_status

  if [[ ${RC} == 0 ]]; then
    ret_status="${_omb_prompt_gray}❯"
  else
    ret_status="${_omb_prompt_brown}❯"
  fi

  history -a
  # Keep the prompt and command output thin, but type commands at medium weight.
  PS1="$(clock_prompt)$python_venv${hostname} ${_omb_prompt_teal}\W${git_branch}\n${ret_status} ${_omb_prompt_normal}\[\e[1m\]"
  PS0='\[\e[0m\]'
}

_omb_util_add_prompt_command _omb_theme_PROMPT_COMMAND
EOF
}

write_extra_completions() {
  local custom_dir="$HOME/.oh-my-bash/custom"

  mkdir -p "$custom_dir"

  cat > "$custom_dir/codex-completions.sh" <<'EOF'
#! bash oh-my-bash.module
#
# Extra completions for cloud, Terraform, Kubernetes, and Python tooling.
#

if declare -F _omb_module_require_completion >/dev/null 2>&1; then
  _omb_module_require_completion awscli terraform kubectl helm minikube pip pip3 uv
fi

EOF
}

# Install Oh My Bash (official installer)
if [[ ! -d "$HOME/.oh-my-bash" ]]; then
  bold "Installing Oh My Bash..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/ohmybash/oh-my-bash/master/tools/install.sh" -o "$tmp/install-omb.sh"
  bash "$tmp/install-omb.sh" --unattended
else
  ok "Oh My Bash already installed."
fi

write_two_line_font_theme
write_extra_completions

# Ensure ~/.bashrc exists
touch "$HOME/.bashrc"

# Make login shells load ~/.bashrc too.
cat > "$HOME/.bash_profile" <<'EOF'
# Load interactive Bash settings from ~/.bashrc.
if [[ -f "$HOME/.bashrc" ]]; then
  source "$HOME/.bashrc"
fi
EOF

# Persist silence deprecation warning (macOS) in bashrc (instead of exporting only in this script)
if ! grep -qE '^[[:space:]]*export[[:space:]]+BASH_SILENCE_DEPRECATION_WARNING=' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport BASH_SILENCE_DEPRECATION_WARNING=1\n' >> "$HOME/.bashrc"
fi

# Add pbcopy alias (Linux) if pbcopy doesn't exist
# - On macOS pbcopy already exists, so we do nothing.
# - On Linux we map pbcopy to xclip or wl-copy if available.
if ! grep -qE '^[[:space:]]*alias[[:space:]]+pbcopy=' "$HOME/.bashrc" 2>/dev/null; then
  cat >> "$HOME/.bashrc" <<'EOF'

# pbcopy compatibility (managed)
if ! command -v pbcopy >/dev/null 2>&1; then
  if command -v wl-copy >/dev/null 2>&1; then
    alias pbcopy='wl-copy'
  elif command -v xclip >/dev/null 2>&1; then
    alias pbcopy='xclip -selection clipboard'
  elif command -v xsel >/dev/null 2>&1; then
    alias pbcopy='xsel --clipboard --input'
  fi
fi
EOF
fi

cat >> "$HOME/.bashrc" <<'EOF'

__codex_answer () {
  if [ $# -gt 0 ]; then
    codex --ask-for-approval never exec \
      --model gpt-5.6-luna \
      -c model_reasoning_effort=\"medium\" \
      --sandbox read-only \
      --skip-git-repo-check \
      --output-last-message "$out" \
      "$*" \
      >/dev/null 2>"$err"
  else
    codex --ask-for-approval never exec \
      --model gpt-5.6-luna \
      -c model_reasoning_effort=\"medium\" \
      --sandbox read-only \
      --skip-git-repo-check \
      --output-last-message "$out" \
      - \
      >/dev/null 2>"$err"
  fi

  rc=$?
  [ -s "$out" ] && cat "$out"
  if [ $rc -ne 0 ] && [ -s "$err" ]; then
    cat "$err" >&2
  fi
  rm -rf "$d"
  return $rc
}

alias '??'='__codex_answer'
alias k='kubectl'
alias tf='terraform'
alias v='nvim'

EOF

if ! grep -q "BEGIN MAIN TERMINAL SETUP" "$HOME/.bashrc" 2>/dev/null; then
  cat >> "$HOME/.bashrc" <<'EOF'

# BEGIN MAIN TERMINAL SETUP
export PATH="$HOME/.local/bin:$PATH"
export TERMINAL="alacritty"

alias term="alacritty"
alias terminal="alacritty"
alias alac="alacritty"
# END MAIN TERMINAL SETUP
EOF
fi

if ! grep -q "BEGIN CODEX READLINE KEYBINDINGS" "$HOME/.bashrc" 2>/dev/null; then
  cat >> "$HOME/.bashrc" <<'EOF'

# BEGIN CODEX READLINE KEYBINDINGS
if [[ $- == *i* ]]; then
  bind '"\e[1;5D": backward-word'
  bind '"\e[5D": backward-word'
  bind '"\e[1;5C": forward-word'
  bind '"\e[5C": forward-word'
  bind '"\e[1;3D": backward-word'
  bind '"\e[1;3C": forward-word'
fi
# END CODEX READLINE KEYBINDINGS
EOF
fi


# --- Nerd Font install (before terminal theme import) ---
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    bold "Installing Nerd Font (JetBrainsMono Nerd Font) via Homebrew..."
    brew install --cask font-jetbrains-mono-nerd-font || true
  else
    warn "Homebrew not found. Install a Nerd Font manually (JetBrainsMono Nerd Font) on macOS."
  fi
fi


bold $'\n=== Done ==='
ok "1) Close ALL terminals and reopen."
ok "2) Log out/in to ensure your login shell is bash."
ok "3) Verify:"
echo "   echo \$SHELL"
echo "   bash --version"
echo
ok "Your backups are in: $BACKUP_DIR"
warn "If you want to restore: copy files back from that folder into \$HOME."

# That suppresses the “Last login” banner in new Terminal sessions.
touch ~/.hushlogin
