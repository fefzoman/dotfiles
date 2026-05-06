#!/usr/bin/env bash
set -euo pipefail

ts="$(date +%Y%m%d%H%M%S)"
BACKUP_DIR="$HOME/.shell-reset-backup/$ts"
mkdir -p "$BACKUP_DIR"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m%s\033[0m\n" "$*"; }

move_to_backup() {
  local p="$1"
  if [[ -e "$p" || -L "$p" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "${p#$HOME/}")" 2>/dev/null || true
    bold "Backing up: $p  ->  $BACKUP_DIR/"
    mv -f "$p" "$BACKUP_DIR/" || true
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

install_pkgs() {
  local pkgs=("$@")
  local sudo=""
  if [[ $EUID -ne 0 ]]; then
    have sudo && sudo="sudo" || sudo=""
  fi

  if have apt-get; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo apt-get update -y || true
    $sudo apt-get install -y "${pkgs[@]}" || true
  elif have dnf; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo dnf install -y "${pkgs[@]}" || true
  elif have pacman; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo pacman -Sy --noconfirm "${pkgs[@]}" || true
  elif have zypper; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo zypper install -y "${pkgs[@]}" || true
  elif have brew; then
    brew install "${pkgs[@]}" || true
  else
    warn "No supported package manager detected. Install dependencies manually: git curl wget dconf-cli"
  fi
}

bold "=== 1) Reset Bash/Zsh customizations (backup + clean start) ==="
# Bash dotfiles
move_to_backup "$HOME/.bashrc"
move_to_backup "$HOME/.bash_profile"
move_to_backup "$HOME/.bash_login"
move_to_backup "$HOME/.profile"
move_to_backup "$HOME/.inputrc"
move_to_backup "$HOME/.bash_aliases"

# Zsh dotfiles / frameworks
move_to_backup "$HOME/.zshrc"
move_to_backup "$HOME/.zprofile"
move_to_backup "$HOME/.zshenv"
move_to_backup "$HOME/.zlogin"
move_to_backup "$HOME/.zlogout"
move_to_backup "$HOME/.oh-my-zsh"
move_to_backup "$HOME/.zinit"
move_to_backup "$HOME/.antigen"
move_to_backup "$HOME/.p10k.zsh"
move_to_backup "$HOME/.config/starship.toml"

# Bash frameworks
move_to_backup "$HOME/.oh-my-bash"
move_to_backup "$HOME/.bash_it"

ok "Backups stored in: $BACKUP_DIR"
warn "If you use chezmoi (or similar), it may re-apply old dotfiles after this."

bold $'\n=== 2) Switch login shell to Bash (disable Zsh as default) ==='
BASH_PATH="$(command -v bash || true)"
if [[ -z "${BASH_PATH}" ]]; then
  warn "bash not found in PATH. Aborting."
  exit 1
fi

if [[ "${SHELL:-}" != "$BASH_PATH" ]]; then
  if have chsh; then
    bold "Attempting: chsh -s $BASH_PATH"
    if chsh -s "$BASH_PATH" >/dev/null 2>&1; then
      ok "Login shell set to bash. (You must log out/in for it to fully take effect.)"
    else
      warn "chsh failed (often needs your password or admin policy). Run manually:"
      warn "  chsh -s $BASH_PATH"
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
OMB_PROMPT_CONDAENV_FORMAT='(%s) '
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
    ret_status="${_omb_prompt_purple}➤"
  else
    ret_status="${_omb_prompt_brown}➤"
  fi

  history -a
  PS1="$(clock_prompt)$python_venv${hostname} ${_omb_prompt_teal}\W${git_branch}\n${ret_status} ${_omb_prompt_normal}"
}

_omb_util_add_prompt_command _omb_theme_PROMPT_COMMAND
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

__codex_answer () {
  local d out err rc
  d="$(mktemp -d -t codex.XXXXXX)"
  out="$d/answer.txt"
  err="$d/stderr.log"

  if [ $# -gt 0 ]; then
    codex --ask-for-approval never exec \
      --model gpt-5.5 \
      -c model_reasoning_effort=\"medium\" \
      --sandbox read-only \
      --skip-git-repo-check \
      --output-last-message "$out" \
      "$*" \
      >/dev/null 2>"$err"
  else
    codex --ask-for-approval never exec \
      --model gpt-5.5 \
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
alias tf='terraform'
alias v='nvim'
